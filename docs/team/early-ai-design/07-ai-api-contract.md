# 07 — AI API Contract (for backend & frontend)

> Owner: AI team. Consumers: backend (bomboe) calls these endpoints; frontend (David V.) renders
> the results it gets from the backend. **Status: DRAFT** — must be agreed with bomboe (see
> DGAREADME1.md, decision P-02).

## 1. Principles

- The AI service is **stateless**: the backend sends a **context bundle** with each request and
  stores everything. The AI service only computes and returns decisions + proposed actions.
- The AI service **never writes** to the DB and never contacts other users. The backend validates
  and applies `actions[]`.
- All amounts are in **lei (RON)** as numbers with 2 decimals. All timestamps are ISO-8601 with
  timezone (`Europe/Bucharest`). IDs are strings.
- Every request carries `as_of` (the simulated "now"), so the demo clock is controllable.
- Base path: `/v1`. JSON only. Errors: `{ "error": { "code": "...", "message": "..." } }`.

## 2. Endpoints

| Method & path | Called when | Returns |
|---|---|---|
| `POST /v1/transactions/evaluate` | a new transaction is booked | decision, annotation, optional question, forecast |
| `POST /v1/conversations/answer` | user answered a question (transcript or quick reply) | interpretations, actions, reply, forecast before/after |
| `POST /v1/context/volunteer` | user pressed the mic and said something on their own | same shape as `answer` |
| `POST /v1/goals/forecast` | home screen load, after any applied action | probability, roadmap, drivers |
| `POST /v1/goals/what-if` | "Îmi permit X?" | probability before/after for a scenario |
| `POST /v1/onboarding/interpret` | onboarding conversation answers | initial facts + signatures |
| `POST /v1/facts/signatures` | a fact was added/edited manually in the profile screen | signatures for that fact |
| `POST /v1/chat` | free-form agent conversation (agent path) | reply + proposed actions |
| `GET  /v1/health` | monitoring | `{ "status": "ok" }` |

Voice (STT/TTS) endpoints are **not decided yet** (see `02-system-architecture.md` §5).

## 3. Context bundle (sent by backend in every request)

```json
{
  "as_of": "2026-06-15T13:10:00+03:00",
  "user": { "id": "u_matei", "first_name": "Matei", "language": "ro" },
  "facts": [ "Fact (03 §3)" ],
  "signatures": [ "Signature (03 §4)" ],
  "rules": [ "PatternRule (§5)" ],
  "goals": [ { "id": "goal_01", "name": "Fond 10.000", "target": 10000, "deadline": "2026-12-31",
               "saved": 5200, "deadline_type": "soft" } ],
  "pots": [ { "id": "pot_01", "name": "Vacanță august", "target": 3000, "saved": 1000,
              "deadline": "2026-08-01", "monthly_contribution": 1000 } ],
  "receivables": [ { "id": "rcv_01", "amount": 400, "debtors": ["colegi"], "created_at": "...",
                     "expected_by": "2026-06-30", "status": "open" } ],
  "fixed_costs": [ { "name": "chirie", "amount": 2000, "day": 1 } ],
  "income": { "type": "salary", "amount": 7000, "day": 10 },
  "transactions": [ "Transaction (§4), last 180 days, with annotations" ],
  "question_log": [ { "date": "2026-06-14", "txn_id": "txn_0901", "answered": true } ],
  "probability_history": [ { "date": "2026-06-08", "probability": 0.72 } ]
}
```

## 4. Transaction

```json
{
  "id": "txn_0918",
  "booked_at": "2026-06-15T13:05:00+03:00",
  "amount": 500.00,
  "currency": "RON",
  "merchant_raw": "MEGA IMAGE 0451 BUCURESTI",
  "mcc": "5411",
  "channel": "card_present",
  "items": [ { "name": "sandvișuri", "qty": 5, "amount": 150 } ],
  "annotation": null
}
```

`annotation` (filled after evaluation/answer): `{ "category", "purpose", "effective_amount",
"explanation", "source": "auto|rule|answer|user_edit", "confidence" }`.

## 5. PatternRule

```json
{
  "id": "rule_03",
  "match": { "category": "restaurants", "weekday": [5], "time_window": ["12:00", "15:00"],
             "amount_range": [60, 130], "merchant": null },
  "outcome": { "purpose": "social_connection", "label": "Prânz cu echipa", "own_share_ratio": 1.0 },
  "confidence": 0.9, "hits": 3, "misses": 0, "created_from": "utt_0044", "active": true
}
```

## 6. `POST /v1/transactions/evaluate`

Request: `{ "context": ContextBundle, "transaction": Transaction }`

Response:

```json
{
  "decision": "ask_now",
  "annotation": { "category": "groceries", "purpose": "unknown", "effective_amount": 500,
                  "explanation": "De ~6× coșul tău obișnuit la Mega", "source": "auto", "confidence": 0.3 },
  "scores": { "raw_anomaly": 0.80, "life_fit": 0.10, "rule_match": 0, "unexplained": 0.72 },
  "question": {
    "id": "q_0918",
    "text": "Am văzut 500 lei la Mega azi, mai mult ca de obicei. Ce a fost?",
    "quick_replies": ["Doar pentru mine", "Și pentru alții", "Ceva planificat", "Prefer să nu spun"],
    "expires_at": "2026-06-16T13:10:00+03:00"
  },
  "forecast": { "goal_id": "goal_01", "probability_before": 0.78, "probability_provisional": 0.71 },
  "actions": [ { "type": "annotate_transaction", "params": { "...": "..." }, "requires_confirmation": false } ]
}
```

`decision` ∈ `ignore | auto_classify | inform | ask_now | ask_later`. For `inform`, `question` is
null and `inform_text` contains the quiet card text.

## 7. `POST /v1/conversations/answer` (and `/v1/context/volunteer`)

Request:

```json
{
  "context": "ContextBundle",
  "question_id": "q_0918",
  "transaction_id": "txn_0918",
  "input": { "type": "voice_transcript", "text": "Am luat și pentru colegi, suntem cinci." }
}
```

`input.type` ∈ `voice_transcript | text | quick_reply`. For `/context/volunteer`, `question_id` and
`transaction_id` are null.

Response:

```json
{
  "interpretations": [
    { "intent": "SHARED_PURCHASE", "purpose": "on_behalf_of_others", "beneficiary": "shared",
      "persistence": "one_off", "planned": false, "confidence": 0.94,
      "entities": { "people_count": 5 } }
  ],
  "actions": [
    { "id": "a1", "type": "annotate_transaction", "requires_confirmation": false,
      "params": { "txn_id": "txn_0918", "purpose": "on_behalf_of_others", "effective_amount": 100,
                  "explanation": "Ai luat și pentru 4 colegi" } },
    { "id": "a2", "type": "create_receivable", "requires_confirmation": false,
      "params": { "txn_id": "txn_0918", "amount": 400, "debtors": ["colegi"], "expected_by": "2026-06-30" } },
    { "id": "a3", "type": "propose_payment_request", "requires_confirmation": true,
      "params": { "receivable_ref": "a2", "recipients_count": 4, "amount_each": 100 } },
    { "id": "a4", "type": "create_rule", "requires_confirmation": false,
      "params": { "match": { "merchant": "Mega Image", "weekday": [1,2,3,4,5], "time_window": ["12:00","14:30"] },
                  "outcome": { "purpose": "on_behalf_of_others", "label": "Prânz pentru echipă" },
                  "confidence": 0.5 } }
  ],
  "follow_up": null,
  "reply": { "text": "Am înțeles! Cheltuiala ta reală e 100 lei. Ai 400 lei de recuperat de la colegi — vrei să le trimit cererea de plată?",
             "speak": true },
  "forecast": { "goal_id": "goal_01", "probability_before": 0.71, "probability_after": 0.77 },
  "plan_diff": { "changed": ["receivables", "groceries_effective"], "reason": "SHARED_PURCHASE on txn_0918" }
}
```

`follow_up` (optional, max one): `{ "type": "tap_card", "text": "Partea ta a fost ~100 lei?",
"options": ["Da", "Altă sumă"] }` — used when the own share was estimated, not stated.

## 8. `POST /v1/goals/forecast` / `POST /v1/goals/what-if`

Request: `{ "context": ContextBundle, "goal_id": "goal_01", "scenario": null }`
`scenario` (what-if): `{ "changes": [ { "type": "purchase", "amount": 2500, "date": "2026-06-20", "category": "electronics" } ] }`

Response: the Monte Carlo output from `06-goal-engine.md` §4 + the roadmap object (§7 there) +
`options[]` (§6 there) when relevant.

## 9. Action types (full list)

See `05-conversation-and-actions.md` §5. Backend contract for each action:

- Apply in the order returned; `params` may reference earlier actions by `id` (e.g. `receivable_ref: "a2"`).
- `requires_confirmation: true` → do **not** apply; show it in the UI; apply only after the user taps.
- After applying, call `/v1/goals/forecast` to refresh the home screen.

## 10. Latency budget (demo)

| Step | Target |
|---|---|
| `/transactions/evaluate` (incl. question phrasing) | < 2 s (template fallback at 2 s) |
| `/conversations/answer` | < 3 s |
| `/goals/forecast` | < 300 ms |
