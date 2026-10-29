# 08 — Synthetic Personas, Data Generation & Demo Script

> Owner: AI team (data generator: danutu; demo script: whole team). All people, numbers and products
> here are **fictional** (as the challenge requires). Numbers are starting values — tune them so the
> simulator gives the probabilities we want to show.

## 1. Demo clock

The pitch talks about "10.000 lei până la 31 decembrie" and "vacanță în august". On the real
hackathon date (28 Oct) August is past and December is 2 months away, so the demo uses a
**simulated "now"**: proposed `as_of = 2026-06-15` (a Monday). Every API call carries `as_of`
(doc 07 §1), so we can change it in one place.

## 2. Personas

### P1 — Matei (main demo persona)

| Field | Value |
|---|---|
| Age / job | 26, junior software developer, office 3 days/week, București |
| Income | 7.000 lei net on the 10th; meal tickets 40 lei/working day |
| Housing | rents alone, 2.000 lei on the 1st |
| Fixed costs | utilities ~350, phone 60, Spotify 25, gym 180 |
| Patterns | Mega Image near the office 3–4×/week, median basket 85 lei; Friday team lunch 60–110 lei (will become a learned rule) |
| Goal | 10.000 lei by 31 Dec 2026 (soft), saved 5.200 on 15 June |
| Protected | concerts / festivals |
| Demo transaction | Mega Image 500 lei, Monday 13:05 → "am luat și pentru colegi, suntem cinci" |

### P2 — Andrei (context contrast: TV = work tool)

| Field | Value |
|---|---|
| Age / job | 31, sports analyst (employee), works from home |
| Facts | confirmed occupation fact with signatures: electronics (TV/monitor) + sports streaming = `work_tool` |
| Patterns | two sports streaming subscriptions (overlap → optimisation hint), football tickets |
| Demo transaction | eMAG TV 4.500 lei → **no question**, inform card: "Am trecut televizorul la Echipament de lucru" |

### P3 — Bianca (same TV, different life)

| Field | Value |
|---|---|
| Age / job | 22, student + part-time barista, Iași |
| Income | 2.800 lei, irregular tips |
| Demo transaction | the **same** eMAG TV 4.500 lei → question → "am cedat, era la reducere" → `unplanned_discretionary`, no judgment, route recalculated |

### P4 — Ioana (household scaling)

| Field | Value |
|---|---|
| Age / job | 38, accountant, Cluj; partner + 2 children (7 and 11) → equivalence 2.1 |
| Patterns | Shop&Go almost daily + weekend big shop; median basket 140 |
| Expected events | school supplies Aug–Sep, Easter, 1 Iunie, Christmas |
| Demo transaction | Shop&Go 350 lei → **no question** (normal for this household); same basket for Matei → question |

### P5 — Radu (optional: irregular income)

| Field | Value |
|---|---|
| Age / job | 29, freelance designer (PFA) |
| Income | 4.000–12.000 lei/month, irregular |
| Point | wider probability band; laptop/camera = `work_tool`; agent explains why the forecast is less certain |

## 3. Data generator (`ai/scripts/generate_data.py`)

Per persona config (YAML/JSON) → 6 months of transactions before `as_of`:

- **Recurring**: salary, rent, utilities, subscriptions — fixed day, small noise.
- **Category streams**: for each category, visits per week (Poisson) × basket amount (lognormal
  around the persona median), with weekday/time preferences (e.g. Mega at lunch on weekdays).
- **Patterns**: Friday team lunch; weekend big shop for Ioana.
- **Seasonal events**: Easter (Orthodox Easter 2026 = 12 April), 1 Iunie for parents.
- **Receipt items** for a few transactions (demo bonus).
- **Seeded** RNG → same data every run.
- Output: `data/personas/<id>/profile.json`, `transactions.json`, `facts.json` (Andrei's occupation
  fact is pre-confirmed; others are discovered in the demo).

## 4. Mock product catalogue (`data/products.json`)

Fictional products, fictional rates, clearly labelled as mock in the UI:

| Product | Use | Example rule for recommendation |
|---|---|---|
| Pușculiță flexibilă | short goals, withdraw any time | goal < 3 months or uncertain amount |
| Cont de economii | medium goals | 3–12 months |
| Depozit la termen 6 luni | money not needed before deadline | goal ≥ 6 months and amount fixed |

## 5. Demo script

### Scene A — the 60-second pitch demo (must be bulletproof)

1. Home: Matei, goal bar **78%** ("față de 72% săptămâna trecută").
2. Presenter clicks "Simulează tranzacție" → feed: **Mega Image −500 lei**; bar drops to **71%** (provisional, "în așteptare").
3. Agent speaks: "Am văzut 500 lei la Mega azi, mai mult ca de obicei. Ce a fost?"
4. Presenter: "Am luat și pentru colegi, suntem cinci."
5. Screen: 500 → **100 lei** · card **"400 lei de recuperat"** · "Trimit cererea de plată?" · bar goes up to **77%**.
6. Agent: "Am înțeles! Cheltuiala ta reală e 100 lei…"

Fallbacks: if the mic fails → tap "Și pentru alții" chip + tap card "suntem 5"; if the LLM fails →
template question + deterministic quick-reply interpretation. Rehearse with the stage noise in mind.

### Scene B — "same purchase, different life" (30 s, our differentiator)

Split screen: Andrei vs Bianca, same TV 4.500 lei. Andrei: no question, "Echipament de lucru — știu
că analizezi meciuri". Bianca: gentle question → "am cedat" → recalculated, no judgment.

### Scene C — planned event (20 s)

Matei presses the mic: "În august merg în vacanță, cam 3.000 lei." → pot "Vacanță august",
1.000 lei/month for 3 months (one tap to confirm) → later the flight ticket is drawn from the pot.

### Scene D — learning (15 s)

Third Friday team lunch → no question; feed label "Prânz cu echipa" + "Nu te mai întreb de asta".

### Scene E — life change (optional)

Ioana: "De luna asta stă și mama la noi." → temporary household change → groceries baseline
rescaled → plan diff with options.
