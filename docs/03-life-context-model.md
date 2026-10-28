# 03 — Life Context Model (the core of CashGuard)

> Owner: AI team (David G. + danutu). This is the most important document in the repo.
> Everything else (anomaly detection, questions, goal roadmap) depends on it.

## 1. The principle

**A purchase has no value on its own. Its meaning is a function of `(purchase, person, moment)`.**

- A 4.500 lei TV is a *work tool* for a sports analyst, a *treat* for a student, and a
  *replacement* for someone whose TV broke last week.
- A 350 lei Shop&Go basket is *normal* for a family of 4, and *unusual* for someone who lives alone.
- 600 lei of running shoes is a *need* for a marathon runner whose last pair is 7 months old,
  and a *treat* ("am cedat, mi-am luat adidași") for someone who doesn't run.

So CashGuard **never** labels a purchase as good or bad. It assigns a **purpose** (why this money
was spent, in this person's life) and a **life-fit score** (how well the person's life explains it).
Only purchases that are *large for this person* **and** *not explained by their life* lead to a question.

> Honest constraint: context changes the **interpretation** and whether we **ask**. It does not make
> money disappear. A work-tool TV still lowers the cash available for the goal; the agent says so
> neutrally ("Am trecut televizorul la Echipament de lucru. Traseul tău: 76%").

## 2. What we model about a person (the Life Profile)

The Life Profile is a set of **facts**. Each fact is one statement about the person's life.

| Layer | Examples of facts | Why it matters for spending |
|---|---|---|
| Identity & work | occupation, employee / PFA / freelancer, remote / office, industry | defines *work tools* (TV, laptop, camera, software) and income pattern |
| Income pattern | salary day, fixed vs irregular, meal tickets (tichete de masă), bonuses, 13th salary | cash-flow timing, variance of the forecast |
| Household | adults, children + ages, elderly dependents, pets, who pays what | scales groceries, pharmacy, clothing; creates seasonal events (school) |
| Housing | rent / own / with parents, rent amount, city | fixed costs, cost-of-living level |
| Mobility | car (fuel type), public transport pass, bike, commute distance | fuel, parking, RCA/ITP yearly events |
| Activities & interests | running 3×/week, gaming, photography, football with friends, festivals | explains equipment, subscriptions, tickets; replacement cycles |
| Social patterns | Friday team lunch, Sunday family dinner, paying for the group | recurring restaurant/grocery spikes, shared purchases → receivables |
| Upcoming life events | vacation in August, wedding in June, baby due, moving, exams | planned spending → savings pots, not anomalies |
| Values & priorities | "travel matters to me", "I want to cut food delivery" | which categories are **protected** (never cut first) and which the user wants to reduce |
| Goals | 10.000 lei by 31 Dec, emergency fund, car down payment | the roadmap the agent optimises |

**Sensitive data rule (GDPR Art. 9 spirit):** we never *infer* health, religion, ethnicity, sexual
orientation or political views from transactions. If the user volunteers something (e.g. "e pentru
tratamentul mamei"), we store only the financial consequence (`purpose: household_care`,
`essential: true`), and we never ask questions about pharmacy/medical transactions.

## 3. The Fact object

```json
{
  "id": "fact_occ_01",
  "type": "occupation",
  "value": { "title": "analist sportiv", "employment": "employee", "work_mode": "remote" },
  "text": "Sunt analist sportiv, lucrez de acasă",
  "source": "user_voice",
  "status": "confirmed",
  "confidence": 0.95,
  "persistence": "permanent",
  "valid_from": "2026-01-01",
  "valid_to": null,
  "evidence": ["utt_0012", "txn_0451"],
  "signature_ids": ["sig_occ_01_a", "sig_occ_01_b", "sig_occ_01_c"],
  "created_at": "2026-06-02T18:20:00+03:00",
  "updated_at": "2026-06-02T18:20:00+03:00"
}
```

Field rules:

- `source`: `onboarding` | `user_voice` | `user_text` | `user_edit` | `inferred_from_transactions`.
- `status`: `hypothesis` (inferred, unconfirmed) → `confirmed` (user said / confirmed) → `expired`
  (temporary fact past `valid_to`) or `rejected` (user said no — never re-proposed).
- `confidence`: confirmed by the user = 0.9–1.0; inferred = 0.3–0.7 depending on evidence.
- `persistence`: `permanent` | `temporary` (has `valid_to`) | `recurring` (e.g. yearly birthday).

### Fact types (initial list, extendable)

`occupation`, `employment_type`, `income`, `meal_tickets`, `household_member`, `pet`, `housing`,
`city`, `vehicle`, `commute`, `activity`, `subscription_need`, `social_pattern`, `life_event`,
`priority` (protected / reduce), `goal`, `custom` (free text the LLM couldn't map — still stored).

## 4. Spending Signatures — how a fact "predicts" money

A fact is useless to the math unless it says something concrete about spending. Each fact owns
one or more **signatures**: structured predictions of what this fact means for transactions.

```json
{
  "id": "sig_occ_01_a",
  "fact_id": "fact_occ_01",
  "effect": "explains",
  "category": "electronics",
  "merchant_hints": ["eMAG", "Altex", "Flanco", "Media Galaxy"],
  "item_keywords": ["televizor", "TV", "monitor", "laptop", "soundbar"],
  "amount_range": [1500, 9000],
  "replacement_cycle_days": 900,
  "purpose": "work_tool",
  "strength": 0.9
}
```

### The four signature effects

| Effect | What it does | Example |
|---|---|---|
| `explains` | A matching transaction gets this purpose; reduces anomaly | sports analyst → TV / sports streaming = `work_tool` |
| `scales_baseline` | Changes the *expected amount* of a category | family of 4 → groceries ×2.1 (see §6) |
| `expects_event` | Predicts a dated/seasonal expense | children → school supplies (rechizite) mid-Aug → mid-Sep; vacation in August → travel spend in Jul–Aug |
| `suppresses_question` | A learned pattern that should not be asked about again | Friday 12:00–15:00 restaurant 60–130 lei → "prânz cu echipa" |

`replacement_cycle_days` models **need saturation**: if the same kind of item was bought recently,
the signature explains a new one much less (a second TV 2 months later is not obviously a work need).

### Where signatures come from

1. **Signature Library (deterministic, curated by us)** — ~40 common facts with hand-written
   signatures: household sizes, kids by age, pets, car, public transport, common hobbies (running,
   gym, cycling, gaming, photography, music festivals), common occupations (developer, teacher,
   designer, driver, student, sports analyst for the demo), Romanian calendar events (Paște,
   Crăciun, 1 Iunie, 8 Martie / Mărțișor, start of school, Black Friday in November, 31 March
   local taxes). Fast, predictable, demo-safe.
2. **LLM-generated signatures** for anything not in the library ("fac cosplay", "am un PFA de
   fotografie", "antrenez o echipă de copii la fotbal"). The LLM maps free text into the **same
   JSON schema** (validated with structured outputs, see `09-llm-integration.md`). Generated
   **once when the fact is created**, stored, and reused — never per transaction.

This combination is what makes the personalisation unlimited while staying predictable.

## 5. Correlating a transaction with the life (life-fit)

For every transaction `t` and every active signature `s` of type `explains`:

```
match(t, s) =  0.35 · category_match          (1 if t.category == s.category)
             + 0.20 · merchant_match          (1 if t.merchant in s.merchant_hints)
             + 0.20 · item_match              (1 if any item/keyword matches; 0 if no item data)
             + 0.15 · amount_in_range         (1 inside range, linear decay to 0 at 2× outside)
             + 0.10 · time_match              (seasonality / weekday / time window, 1 if no constraint)

saturation(t, s) = min(1, days_since_last_similar_purchase / s.replacement_cycle_days)   (1 if none)

fit(t, s) = match(t, s) · s.strength · fact.confidence · saturation(t, s)

life_fit(t) = max over all signatures s of fit(t, s)        ∈ [0, 1]
```

Two more sources of explanation are combined with `max(...)`:

- **Personal precedent**: the user already explained a *similar* transaction (same category, same
  merchant or amount band ±30%) → `precedent_fit = 0.8 · similarity`.
- **Planned events / pots**: the transaction matches an active pot or `expects_event` signature
  (e.g. flight tickets while a "Vacanță august" pot exists) → it is drawn from the pot, `life_fit ≈ 0.9`.

The highest-scoring source also produces the **explanation string** stored on the transaction —
every classification has a "because":

> "Nu te-am întrebat de televizor pentru că mi-ai spus pe 2 iunie că ești analist sportiv."

### Context precedence (when sources disagree)

1. The user's explicit answer about **this** transaction
2. A learned personal rule (from earlier answers)
3. A confirmed fact's signature
4. An inferred (hypothesis) fact's signature — weight capped by its lower confidence
5. Population prior (synthetic segment data)

An inferred fact can **never** override something the user said.

## 6. Context-adjusted baselines ("family of 4 spends more at Shop&Go")

Baselines are what "normal" means **for this person**. Anomalies are measured against them.

### 6.1 Household scaling — OECD-modified equivalence scale

| Household member | Weight |
|---|---|
| First adult | 1.0 |
| Each additional person aged 14+ | 0.5 |
| Each child under 14 | 0.3 |

Family of 4 (2 adults + 2 children under 14) = 1.0 + 0.5 + 0.3 + 0.3 = **2.1**.
So the *prior* expectation for household categories (groceries, household goods, pharmacy basics,
utilities share) is `single_adult_prior × 2.1`.

Categories that scale with household: `groceries`, `household_goods`, `pharmacy_basic`,
`utilities`, `kids` (only if children), `clothing`. Categories that do **not** scale: `electronics`,
`subscriptions`, `hobbies` (these are driven by activity facts instead).

### 6.2 Blending personal history with the context prior (cold start → personal)

For each category `c` we keep robust statistics of the user's own **effective** amounts
(per transaction: median + MAD; per month: total distribution).

```
expected_c = (n · personal_median_c + k · prior_median_c) / (n + k)        with k = 5
```

- `n` = number of user transactions in category `c` in the last 180 days.
- New user (n = 0) → pure context prior (segment × equivalence scale × city index).
- After ~20 transactions the personal history dominates.

### 6.3 Instant re-scaling on life changes

When a household fact changes (baby born, partner moves in, mother-in-law stays for a month),
we do **not** wait months for history to catch up. We rescale immediately:

```
expected_c_new = expected_c_old · (equivalence_new / equivalence_old)
```

For temporary changes (`valid_to` set) the scaling applies only inside the window.

### 6.4 Keep baselines clean

Baselines are computed on **effective amounts**, not raw card amounts:

- 500 lei at Mega where 400 were for colleagues → the grocery baseline sees **100**.
- Vacation spending drawn from a pot → excluded from the monthly discretionary baseline.
- Fraud / "nu eu am făcut-o" → excluded.

Without this, one shared purchase would inflate "normal" and the next real anomaly would be missed.

## 7. Inferring the life from transactions (hypotheses)

The system proposes facts it sees in the data, but they stay `hypothesis` until confirmed:

| Pattern in transactions | Hypothesis | Confirmation |
|---|---|---|
| Monthly payment to a kindergarten / after-school | has a young child | 1-tap card |
| Regular Petrom / OMV / MOL / Rompetrol | owns a car | 1-tap card |
| Decathlon + race registration fees | runner | 1-tap card |
| Pet shop every month | has a pet | 1-tap card |
| Restaurant every Friday 12–15h | team lunch pattern | learned rule after 2 explanations |
| Rent transfer amount changes | moved / new contract | ask (permanent change) |

Hypotheses are confirmed via **1-tap cards** in the feed (cheap, not counted in the daily voice
question budget). If there is no anomaly to ask about on a given day, the single daily question may
be used for the most valuable open hypothesis instead. Rejected hypotheses are never proposed again.

## 8. Propagation: every life change re-plans the roadmap

```
fact created / changed / expired
      │
      ├─► regenerate affected signatures
      ├─► recompute baselines (§6)          ── e.g. groceries 900 → 1.890 lei/month
      ├─► recompute expected events          ── e.g. school supplies in September
      ├─► recompute pots & fixed costs
      ├─► goal engine: new probability + new monthly roadmap (06-goal-engine.md)
      └─► plan diff + human explanation
            "Pentru că acum sunteți 4 acasă, am mutat bugetul de cumpărături la 1.890 lei/lună.
             Șansa pentru 10.000 lei până la 31 decembrie: 68% (era 79%).
             Variante: mutăm termenul la 15 februarie (82%) sau…"
```

## 9. Example catalogue (same purchase, different life)

| # | Transaction | Person A → result | Person B → result |
|---|---|---|---|
| 1 | TV 4.500 lei, eMAG | Sports analyst → `work_tool`, no question, inform card | Student, no related fact → question |
| 2 | Shop&Go 350 lei | Family of 4 (baseline ×2.1) → normal, nothing | Lives alone, median basket 60 → question |
| 3 | Running shoes 600 lei, Decathlon | Runner, last pair 7 months ago → `self_investment`, nothing | Non-runner → question → "am cedat" → `impulse`, no judgment |
| 4 | Laptop 6.000 lei | Freelance developer (PFA) → `work_tool`, note "posibil deductibil" | Same person, laptop bought 3 months ago → saturation → question |
| 5 | Libris / Diverta 400 lei, late August | Parent of 2 school kids → `expects_event` (rechizite) | No kids → question (maybe a gift) |
| 6 | Fuel 400 lei/week | Car commute 40 km → baseline | No car fact, but active "vacanță" fact → rental car on vacation → pot |
| 7 | Steam 250 lei | Gamer, gaming marked **protected** → `identity_joy`, never cut first | User said "vreau să cheltui mai puțin pe jocuri" → gentle note, no question |
| 8 | Restaurant 600 lei, Friday | Pays for the team, colleagues reimburse → `on_behalf_of_others` + receivable | Date night pattern → `social_connection` |
| 9 | Flowers 200 lei on 8 March | Romanian calendar → `social_connection`, expected for everyone | Same amount on a random day → small, below materiality, nothing |
| 10 | Camera lens 3.000 lei | Photographer with PFA → `work_tool` | Hobby photographer, protected hobby → `identity_joy` |
| 11 | Pet food 250 lei monthly | Has a dog → baseline | — |
| 12 | Groceries 1.200 lei week before Easter | Hosts family for Paște → `expects_event` | — |
| 13 | Flight tickets in February | "Vacanță august" pot exists → drawn from pot | No plan → question → user says "merg în august" → pot created retroactively |
| 14 | Untold ticket 900 lei | Goes every year (learned) → next year a pot is suggested in advance | First time → question |
| 15 | Two sports streaming subscriptions | Sports analyst → `work_tool` (explained) **and** an optimisation hint: "două abonamente se suprapun" | — |

Example 15 is important: "explained" does not mean "ignored". The agent can still find savings
inside explained spending — without ever framing them as mistakes.

## 10. Purpose taxonomy (replaces "good / bad")

| Purpose | Meaning | Default treatment in the plan |
|---|---|---|
| `essential_living` | food, rent, utilities, transport to work, health | fixed/variable essentials, never "cut" suggestions |
| `household_care` | spending for kids, partner, parents, pets | scales with household |
| `work_tool` | earns or protects income | one-off, may be reimbursable/deductible |
| `self_investment` | education, sport equipment for active practice | one-off, positive |
| `identity_joy` | valued hobbies the user marked as important | protected envelope |
| `social_connection` | team lunch, friends, gifts, occasions | recurring/seasonal |
| `planned_event` | spending covered by a pot | drawn from pot, not a deviation |
| `on_behalf_of_others` | paid for others | own share only + receivable |
| `unplanned_discretionary` | a treat, an impulse, "am cedat" | absorbed, route recalculated, zero judgment |
| `emergency` | car broke, urgent repair | essential, suggests an emergency fund |
| `unknown` | not answered | treated as discretionary with low confidence, user can fix later |
