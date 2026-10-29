# 09 — LLM Integration (Claude)

> Owner: David G. Status: **proposal** — provider and model need team confirmation (API key /
> credits available at the hackathon). API details below were checked against the current Claude
> API docs on 2026-10-28.

## 1. Where we call the LLM (and nowhere else)

| Call | When | Output | Effort |
|---|---|---|---|
| `phrase_question` | `decision = ask_now` | `{question_text, quick_replies[]}` | `low` |
| `interpret_answer` | answer / volunteered context | `AnswerInterpretation` (05 §3) | `low` |
| `generate_signatures` | a new free-text fact | `Signature[]` (03 §4) | `medium` |
| `onboarding_interpret` | onboarding answers | `Fact[]` | `medium` |
| `agent_chat` | agent path (05 §8) | reply + proposed actions via read-only tools | `medium` |
| `explain_change` (optional) | after replan | 1–2 sentence explanation using numbers we give it | `low` |

**The LLM never computes money** and never executes actions. It extracts and phrases; code
computes and the backend executes.

## 2. Provider and model

- SDK: official Anthropic Python SDK (`pip install anthropic`), client `anthropic.Anthropic()`
  (reads `ANTHROPIC_API_KEY`).
- Default model: **`claude-opus-5-5`** for every call.
- Speed is controlled with `output_config={"effort": "low" | "medium" | ...}`. On this model
  thinking cannot be turned off and the default effort is `medium` — so set `low` explicitly on the
  real-time calls (question + answer).
- If measured latency of the real-time calls is too high for a natural voice exchange, the team can
  decide to try `claude-haiku-5-5` on those two calls only. Measure first; don't switch blindly.

## 3. Structured outputs (how we get reliable JSON)

Use `client.messages.parse(...)` with a Pydantic model as `output_format`; the result is a
validated object in `response.parsed_output`. Our Pydantic models in `ai/app/schemas.py` are the
single source of truth for both the API (doc 07) and the LLM output.

```python
from anthropic import Anthropic
from app.schemas import AnswerInterpretation

client = Anthropic()

response = client.messages.parse(
    model="claude-opus-5-5",
    max_tokens=2000,
    output_config={"effort": "low"},
    system=SYSTEM_PROMPT_INTERPRET,          # frozen text, no timestamps
    messages=[{"role": "user", "content": build_user_content(context_slice, txn, transcript)}],
    output_format=AnswerInterpretation,
)
interpretation = response.parsed_output
```

API facts to remember (things that changed recently and break old examples):

- No assistant **prefill**, no `temperature` / `top_p` / `top_k` (rejected with 400).
- Forced `tool_choice` (`any` / `tool`) is rejected on this model → for JSON use structured
  outputs; for the agent path use `tool_choice: auto` + `strict: true` tools + a clear instruction.
- Always check `response.stop_reason` before reading content (`refusal`, `max_tokens`).
  The API offers a server-side fallback for refusals (`fallbacks="default"` with beta
  `server-side-fallback-2026-07-01`) — the code owner decides whether to enable it.
- Handle errors with the SDK's typed exceptions (`RateLimitError`, `APIStatusError`,
  `APIConnectionError`), and always have the deterministic fallback ready (templates + chips).

## 4. Prompt caching (cheaper + faster repeated calls)

Caching is a prefix match, in the order `tools → system → messages`. Layout per request:

1. `system`: frozen instructions + few-shot examples (identical bytes on every call).
2. First user block: the user's **context slice** (facts, rules, protected categories) — stable
   for a user during a day → put the cache breakpoint here.
3. Last: the volatile part (this transaction, this transcript, `as_of`).

Never put timestamps or random IDs in the system prompt; serialise JSON with sorted keys.
Verify hits with `response.usage.cache_read_input_tokens`. Note: very short prefixes are not
cached (there is a model-dependent minimum), so caching only matters once the context slice is big.

## 5. Context slice (what the LLM sees)

Not the whole bundle. Selected by code:

- first name, household summary, occupation, active temporary facts (vacation, moving);
- up to 5 facts/rules most related to the transaction's category/merchant;
- the transaction + why it's an anomaly ("de ~6× coșul obișnuit");
- for answers: the question that was asked + the transcript;
- **no** IBANs, card numbers, full names of third parties, exact addresses (data minimisation; the
  demo data is fictional anyway).

## 6. System prompt principles (interpret_answer)

- Role: a calm, friendly financial companion for young people in Romania; Romanian only.
- Task: classify the answer into one or more interpretations (catalogue in 05 §4), extract entities.
- Never judge, never moralise, never give investment advice.
- Never calculate amounts — extract numbers exactly as said ("cinci" → 5, "vreo 3 mii" → 3000).
- If unsure → low confidence + `OTHER`; code will show quick replies.
- Romanian specifics to handle: missing diacritics ("am luat si pt colegi"), slang, code-switching
  ("am dat split cu colegii"), numbers in words, "mii" / "sute".

## 7. Evaluation set (build before the demo)

`ai/tests/eval_answers.jsonl` — 60–100 Romanian utterances with the expected intents/entities:

- 5–10 per intent from 05 §4, plus multi-intent answers, negations ("nu, nu pentru colegi"),
  no-diacritics and slang variants, and off-topic answers.
- Run it after every prompt change; target ≥ 90% intent accuracy, 100% on the demo utterances.
- Also test `phrase_question` outputs against the forbidden-phrase blocklist (05 §2).
