# 05 — Conversation, Answer Understanding & Actions

> Owner: AI team (David G. leads the LLM side). Depends on: 03, 04. Feeds: 06, 07.

## 1. Two conversation modes

| Mode | Trigger | How it runs | Latency target |
|---|---|---|---|
| **Fast path** — answer to an agent question, or volunteered context | user answers by voice / presses the mic | fixed pipeline: LLM interprets → code validates & computes → reply | < 3 s after the user stops talking (excluding STT/TTS) |
| **Agent path** — open questions ("Îmi permit un PS5 luna asta?", "Ce se întâmplă dacă mă mut în Cluj?") | chat / voice outside a question thread | Claude with **read-only tools** in a loop (profile, spending summary, what-if simulation, product catalogue) → proposes actions | a few seconds is fine |

Both modes produce the **same output shape**: interpretations + proposed actions + reply + forecast
before/after. Write actions are always executed by the backend, never by the LLM directly.

## 2. Generating the question (step 7 of 04)

Input to the LLM: the transaction, the 3–5 most relevant facts/rules, the user's first name, and the
reason it's an anomaly ("de ~6× coșul tău obișnuit la Mega"). Output (structured):

```json
{ "question_text": "Am văzut 500 lei la Mega azi, mai mult ca de obicei. Ce a fost?",
  "quick_replies": ["Doar pentru mine", "Și pentru alții", "Ceva planificat", "Prefer să nu spun"] }
```

Rules for the question:

- Romanian, ≤ 18 words, one question, spoken-friendly (it will be read by TTS).
- Open, curious; **at most one** hint taken from context ("A fost pentru echipă?") when a fact or
  precedent makes it likely.
- **Forbidden**: "de ce" (sounds accusatory — use "ce a fost"), "prea mult", "risipă",
  "ar fi trebuit", "iar", "din nou", comparisons with other people, any moralising.
- Post-check in code: regex blocklist on the forbidden phrases → if hit, use the template.
- Template fallback (no LLM / timeout 2 s):
  `"Am văzut {amount} lei la {merchant}. A fost ceva diferit de obicei?"`

`quick_replies` are shown as chips — they are also the fallback if voice fails during the demo.

## 3. Understanding the answer — multi-dimensional, multi-intent

A single label is not precise enough. The LLM returns a **list** of interpretations (one answer can
contain several: "am luat pentru colegi și oricum de luna viitoare mă mut"). Each interpretation is
described on several independent dimensions:

| Dimension | Values |
|---|---|
| `intent` | see §4 |
| `purpose` | taxonomy from 03 §10 |
| `beneficiary` | `self` / `household` / `shared` / `others` / `employer` |
| `persistence` | `one_off` / `temporary` / `recurring` / `permanent` |
| `planned` | `true` / `false` |
| `confidence` | 0–1 |

Plus extracted **entities** (numbers and names only — the LLM never does arithmetic):
`people_count`, `people_names`, `stated_own_amount`, `stated_total`, `event_month`, `event_cost`,
`new_rent`, `recurrence` ("în fiecare vineri"), `reimbursable_by`.

## 4. Intent catalogue

| Intent | Romanian examples | Effects (actions in §5) |
|---|---|---|
| `SHARED_PURCHASE` | "am luat și pentru colegi", "am plătit eu pentru toți, suntem 5" | effective amount = own share; receivable for the rest; propose payment request |
| `PLANNED_FUTURE_EVENT` | "merg în vacanță în august, cam 3.000 lei" | create pot, split cost over remaining months; temporary fact; later spending drawn from pot |
| `PERMANENT_CHANGE` | "m-am mutat, chiria e mai mare", "de acum am mașină" | update fixed cost / fact; full replan with options |
| `UNPLANNED_TREAT` | "am cedat, mi-am luat adidași", "era la reducere" | `unplanned_discretionary`; absorb; recalc route; zero judgment |
| `WORK_EXPENSE` | "televizorul e pentru muncă, sunt analist sportiv" | `work_tool`; create/confirm occupation fact + signatures; maybe ask "îl decontezi?" (only if employee) |
| `REIMBURSABLE` | "o decontez de la firmă" | receivable from employer |
| `HOUSEHOLD_CHANGE` | "suntem 4 acasă", "stă soacra la noi o lună" | household fact (permanent or temporary) → baselines rescaled (03 §6.3) |
| `RECURRING_PATTERN` | "în fiecare vineri mâncăm cu echipa" | learned rule, suppress future questions |
| `GIFT_OR_OCCASION` | "a fost ziua mamei" | `social_connection`; recurring yearly event → reminder / pot next year |
| `EMERGENCY` | "s-a stricat mașina", "urgență la dentist" | `emergency`; suggest emergency fund pot if none |
| `INCOME_CHANGE` | "am primit bonus", "am trecut pe freelancing" | income fact; replan |
| `NOT_ME` | "n-am făcut eu plata asta" | flag suspected fraud → card-freeze flow (confirm), excluded from spending |
| `CORRECTION` | "nu, a fost doar pentru mine" | revert the previous interpretation's actions |
| `DECLINE` | "nu vreau să spun" | respect; `unknown`/private; suppress similar questions |
| `OTHER` | anything else | store as `custom` fact text, no action, polite reply |

## 5. Action catalogue

Actions are **proposals** returned to the backend. The backend validates and applies them
transactionally, then stores the result. Schema in `07-ai-api-contract.md`.

| Action | Params | Needs user confirmation? |
|---|---|---|
| `annotate_transaction` | txn_id, purpose, effective_amount, explanation | no |
| `create_receivable` | txn_id, debtors[], amount, expected_by | no |
| `propose_payment_request` | receivable_id, recipients[], amount_each | **yes** — it is sent to other people |
| `create_pot` | name, target, deadline, monthly_contribution, linked_fact_id | **yes** (one tap) — it moves money |
| `draw_from_pot` | pot_id, txn_id, amount | no |
| `upsert_fact` / `expire_fact` | Fact object / fact_id | no (visible & editable in the profile screen) |
| `create_rule` / `update_rule` | PatternRule | no |
| `update_fixed_cost` | name, amount, from_date | no |
| `schedule_reminder` | text, at | no |
| `flag_suspected_fraud` | txn_id | **yes** — triggers card freeze |
| `recommend_product` | product_id (mock catalogue), reason | shown as a suggestion only |

**Safety rule:** anything that moves money or contacts other people requires an explicit tap by
the user. The agent proposes; the user disposes.

## 6. Deterministic post-processing (code, not LLM)

After the LLM returns its interpretation:

1. **Money math.** Own share for `SHARED_PURCHASE`:
   - user said the amount ("eu am luat de 100") → that amount;
   - user said a count ("suntem 5") → `total / count` (500 / 5 = 100);
   - neither → **estimate from the personal baseline** (median basket at that merchant ≈ 85–100)
     and send a tap card: "Partea ta a fost ~100 lei? [Da] [Altă sumă]".
   Always `0 ≤ own_share ≤ amount`.
2. **Pot math.** `monthly_contribution = (event_cost − already_saved) / months_until_event`. If cost
   unknown → estimate from similar past spending, otherwise one follow-up "Cam cât crezi că o să coste?".
3. **Validation.** Unknown fields dropped, confidence < 0.5 → treated as `OTHER` + quick-reply chips.
4. **Rules.** Create/strengthen rules (04 §8).
5. **Goal engine.** Forecast **before** and **after** applying the actions (06).
6. **Reply.** Generated with the real numbers from steps 1–5 (template or LLM at low effort):
   > "Am înțeles! Cheltuiala ta reală e 100 lei. Ai 400 lei de recuperat de la colegi — vrei să le
   > trimit cererea de plată? Șansa pentru 10.000 lei: 77% (era 71%)."

## 7. Worked example — the 60-second demo

1. Transaction: Mega Image, 500 lei, Monday 13:10 → `unexplained = 0.72` → ask.
2. Agent (voice): "Am văzut 500 lei la Mega azi, mai mult ca de obicei. Ce a fost?"
3. User (voice): "Am luat și pentru colegi, suntem cinci."
4. LLM → `SHARED_PURCHASE`, `beneficiary: shared`, `people_count: 5`, `confidence: 0.94`.
5. Code → own share 100, receivable 400 (4 × 100), rule candidate (Mega, weekday lunch, team).
6. Actions → `annotate_transaction(effective 100)`, `create_receivable(400)`,
   `propose_payment_request(4 × 100)` (needs tap), `create_rule` (candidate, confidence 0.5).
7. Screen: 500 → **100 lei**, "400 lei de recuperat", goal bar goes up.

## 8. Agent path — tools (read-only)

| Tool | Returns |
|---|---|
| `get_profile_summary` | active facts, protected categories, goals |
| `get_spending_summary(period, category?)` | effective totals, baselines, trends |
| `simulate_scenario(changes[])` | goal probability before/after a hypothetical purchase / change |
| `list_products(need)` | items from the **mock** product catalogue (savings account, term deposit, pots) with fictional rates |
| `propose_actions(actions[])` | final step — returns actions to the backend, nothing is executed by the agent |

Example: "Îmi permit un PS5 luna asta?" → `simulate_scenario([{purchase: 2500, month: now}])` →
"Dacă îl iei acum, șansa scade de la 81% la 64%. Dacă aștepți până în ianuarie, rămâi la 79%.
Gaming e pe lista ta de lucruri importante, deci e decizia ta — vrei să fac o pușculiță pentru el?"

This covers two of the hackathon's suggested directions: *support budgeting or saving decisions*
and *compare financial products using customer context* (pot vs deposit for a goal in N months).
