# 04 — Transaction Understanding, Anomaly Detection & Question Policy

> Owner: AI team (calculations part: danutu; context matching: David G.).
> Depends on: `03-life-context-model.md`. Feeds: `05-conversation-and-actions.md`, `06-goal-engine.md`.

## 1. Pipeline for every new transaction

```
transaction arrives (from backend)
  1. normalise       merchant → canonical merchant, MCC → category, optional receipt items
  2. features        amount vs personal baseline, novelty, materiality, frequency, time pattern
  3. context match   life_fit (signatures, precedent, pots) + learned rules     (03 §5)
  4. score           anomaly score → "unexplained" score
  5. decide          ignore | auto_classify | inform | ask_now | ask_later
  6. provisional     goal impact computed with the provisional interpretation
  7. respond         decision + annotation + (optional) question → backend → mobile
```

All of steps 1–6 are **deterministic code** (fast, testable, explainable). The LLM is used only to
*phrase* the question in step 7 (and has a template fallback).

## 2. Normalisation

- **Merchant catalogue** (synthetic, `data/merchants.json`): canonical name, category, typical
  basket, aliases. Romanian examples: Mega Image / Shop&Go (Mega Image's convenience format), Lidl,
  Kaufland, Carrefour, Profi, Penny, Auchan, eMAG, Altex, Flanco, Decathlon, Glovo, Tazz, Bolt,
  Uber, Petrom, OMV, MOL, Rompetrol, Dr.Max, Catena, Sensiblu, Help Net, Libris, Cărturești, Diverta,
  Steam, Netflix, Spotify, Digi, Orange, Vodafone, Enel, Engie, E.ON, CFR Călători, Wizz Air,
  Ryanair, Booking.
- **Categories** (fixed list): `groceries`, `restaurants`, `food_delivery`, `transport`, `fuel`,
  `electronics`, `clothing`, `sport`, `health_pharmacy`, `kids`, `education`, `books`,
  `entertainment`, `subscriptions`, `travel`, `housing_rent`, `utilities`, `telecom`, `gifts`,
  `pets`, `household_goods`, `transfers`, `other`.
- **Receipt items** (optional, demo bonus): synthetic e-receipt line items for some transactions
  ("televizor 55\"", "pâine", "suc ×5"). They make `item_match` in life-fit much more precise.

## 3. Features

| Feature | Formula | Notes |
|---|---|---|
| Robust z-score | `z = (amount − median_c) / (1.4826 · MAD_c)` | per user, per category, on **effective** amounts, context-adjusted (03 §6) |
| Statistical deviation | `stat = clip(z / 4, 0, 1)` | z ≥ 4 → 1 |
| Novelty | `1` if merchant **and** category unseen in 90 days, `0.5` if only merchant new, else `0` | |
| Materiality | `mat = clip(amount / (0.10 · monthly_disposable), 0, 1)` | `monthly_disposable = income − fixed costs`; 10% of it = fully material |
| Frequency deviation | visits this week in category vs weekly median (optional v2) | catches "5 Glovo orders this week" |
| Rule match | `1` if a learned rule matches (weekday, time window, amount range, merchant) | from answers, see 05 §6 |

If MAD = 0 (too little data) we fall back to the context prior's spread.

## 4. Scores

```
raw_anomaly  = 0.5 · stat + 0.2 · novelty + 0.3 · mat                 ∈ [0, 1]
unexplained  = raw_anomaly · (1 − life_fit) · (1 − rule_match)       ∈ [0, 1]
```

Hard filters (checked first — no score needed):

- amount < **materiality floor** = max(50 lei, 1% of monthly income) → `ignore` (just categorise)
- known recurring bill (rent, utilities, subscriptions, loan) within ±10% of the usual amount → `auto_classify`
- category `health_pharmacy` → `auto_classify` as `essential_living`, **never ask**
- transaction already explained by the user (volunteered context, e.g. pot) → `auto_classify`

## 5. Decision table

| Condition | Decision | What the user sees |
|---|---|---|
| hard filter hit | `ignore` / `auto_classify` | category + purpose label in the feed |
| `raw_anomaly ≥ 0.5` **and** `life_fit ≥ 0.6` | `inform` | a quiet card: "Am trecut televizorul la Echipament de lucru — știu că analizezi meciuri. Traseul: 76%." |
| `unexplained ≥ 0.55` and question budget available | `ask_now` | voice question |
| `unexplained ≥ 0.55` but budget used / quiet hours | `ask_later` | queued; may be asked tomorrow if still the most valuable, else expires |
| otherwise | `auto_classify` | normal feed entry with best-guess purpose |

Thresholds (0.5 / 0.6 / 0.55) are **initial values**; tune them on the synthetic personas so that
each persona gets ~2–4 questions per week, never more than 1 per day.

### Worked examples (illustrative numbers)

**Matei, lives alone, Mega Image 500 lei** (median basket 85, MAD 25, disposable 7.000 − 2.615 fixed ≈ 4.385):
`z = 415 / 37 = 11.2 → stat = 1`, `novelty = 0`, `mat = 500/438 → 1`
`raw = 0.5 + 0 + 0.3 = 0.80`, no fact explains it, `life_fit = 0.10` → `unexplained = 0.72` → **ask**.

**Andrei, sports analyst, eMAG TV 4.500 lei**: `raw ≈ 0.80`, `life_fit ≈ 0.86` (occupation
signature, confirmed) → `unexplained ≈ 0.11` → **inform**, no question.

**Bianca, student, same TV**: `raw ≈ 0.85`, `life_fit ≈ 0.05` → `unexplained ≈ 0.81` → **ask**.

**Ioana, family of 4, Shop&Go 350 lei** (family median basket 140, MAD 45, disposable 6.000):
`z = 3.1 → stat = 0.79`, `mat = 0.58` → `raw = 0.57`; weekend-big-shop precedent `life_fit = 0.5`
→ `unexplained = 0.29` → **auto_classify**. Same basket for someone living alone → **ask**.

## 6. Question policy ("don't become annoying")

A companion that interrogates you about every coffee gets uninstalled in 3 days. Hard rules:

1. **Max 1 agent-initiated question per day** (hard cap) and ~4 per week (soft cap).
2. **Only anomalies**: `unexplained ≥ threshold`. Never for small amounts, recurring bills, health.
3. **Pick the most valuable question of the day** when several anomalies compete:
   `priority = unexplained · goal_impact`, where
   `goal_impact = P(goal | best plausible interpretation) − P(goal | worst plausible interpretation)`
   (cheap proxy: amount / remaining amount to goal). Ask the one whose answer changes the plan most.
4. **Quiet hours** 22:00–08:00: questions are queued. For the demo, ask immediately.
5. **Back-off**: if the user ignores 2 questions in a row, the budget drops to 1 question every
   2 days for a week. If they say "nu mai întreba de asta", create a suppression rule for that
   merchant/category.
6. **One follow-up maximum**, in the same thread, and preferably as a **tap card**, not voice
   (e.g. "Partea ta a fost ~100 lei? [Da] [Altă sumă]").
7. **Unanswered after 24h** → default `unplanned_discretionary` with low confidence, no reminder,
   editable later from the feed.
8. **Volunteered context never counts** against the budget (user presses the mic and says
   "merg în vacanță în august").
9. **Tone** (enforced in the prompt + a post-check, see 05 §2): curious, short, never judgmental.

## 7. Provisional impact

Until the user answers, the transaction counts with the **provisional** interpretation
(full amount, `unplanned_discretionary`). The goal bar shows the provisional value with a small
"în așteptare" marker. After the answer, the real interpretation replaces it — in the demo this is
the moment the bar goes back up.

## 8. Learned suppression (so we stop asking)

- If the user explains the **same pattern 2 times** (same category, similar weekday/time, amount
  within ±40%) → create a rule with `confidence 0.7`; after the 3rd confirmation → `0.9` and the
  pattern is auto-classified without asking.
- If the user states recurrence explicitly ("în fiecare vineri mâncăm cu echipa") → create the rule
  immediately with `confidence 0.9`.
- A rule stops applying when a matching transaction is **> 2× the rule's max amount** (that is a
  new situation and may be asked about).
- Rules decay: no hit in 60 days → confidence −0.2; below 0.5 → inactive.

Rule schema is in `07-ai-api-contract.md` (`PatternRule`).
