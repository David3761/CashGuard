# INT · Async agent ports, executor and handlers: report

> Branch `dga-task/async-ports` (from `dga-final` d79a962). Fast mode: built directly, no plan approval. `make check` green: 2502 passed (2501 + 1 new).
> Settles the H-12 open point ("make the shells async when B4 lands (preferred)"): our tool layer is async end to end, so the ports can be implemented directly over bomboe's `AsyncSession` services and danutu's async engine.

## What became `async`

- **Ports** (`app/agent/ports.py`): every Protocol method of the 21 service ports, `EnginePort` and `ContextPort`. `LazyEngine` awaits `app.engine.service`. `LazyContext` awaits the context shells, and still works when a module landing in parallel is sync (`_settle`). C4's pure `library.signatures_for_fact` is sync.
- **Executor**: `execute_tool`, plus its helpers (`_error`, `_log_call`, `_recompute`).
- **Handlers**: the `Handler` type is `Callable[..., Awaitable[dict]]`. Every handler is async, and so are `apply_annotation` (B6's PATCH awaits it), `adder`/`updater`/`remover`'s handlers, `_propagate`, `_active_pot`, `_save` and `_own_share`.
- **Engine stubs** (`app/engine/service.py`): `apply_transaction`, `on_annotation_changed`, `recompute_baselines`, `recompute_plan`, `forecast_goal`, `simulate_plan`, `own_share_estimate`, `auto_save`. The pure `ledger_delta` stays sync.
- **Context shells** (`app/context/service.py`): `evaluate_transaction`, `pick_question`, `on_fact_changed`, `learn_from_annotation`, `infer_hypotheses`, and their loaders (`_transaction`, `_transactions_of_day`, `_context`). `default_reading` and `signatures_for_fact` stay sync (pure).
- **Fakes** (`tests/fakes/fake_services.py`): every port method, `FakeEngine` and `FakeContext`, with the same behaviour as before. The seeding helpers (`FakeTransactions.add`, `Harness.add_tx`) and the `Table` internals stay sync.
- `wiring.py` awaits `execute_tool`. `build_snapshot`, the loop, proactive runs and the fallbacks were already async and are unchanged.

Behaviour is unchanged: the same results, error codes, security rules, D18 plan + forecast, D46 and Scene A. The new test, `test_the_real_engine_and_context_ports_are_awaited`, runs `annotate_transaction` and `add_life_fact` through the real `LazyEngine`/`LazyContext` over the async stubs.

## Merge notes

- **p1a (C8)**: `learn_from_annotation` and `save_rule_change` need `async`. Await `_transaction`/`_context` and bomboe's `pattern_rules.*`. In the tests, monkeypatch `_context`/`_transaction` with an async stand-in (`returning(...)` in `tests/unit/context/test_service_stubs.py`).
- **p1b (C10/C12)**:
  - `infer_hypotheses` and `_rejected_facts` need `async`, and both must await `_context` and `list_rejected`.
  - In `suggest_savings_products`, await `goals.active`, `income_sources.list`, `life_facts.list_active` and `products.list`.
  - The tests await `ok(...)`/`code(...)` and use async stand-ins.
- **int-engine**: on `app/engine/service.py`, take danutu's version (it is already async). These existing mismatches are untouched:
  - the port passes `old`/`new` as Decimals, but his `on_annotation_changed` takes `TxView`s;
  - his `recompute_plan` can return `None` (no goal), and the executor reads `plan.version`.
- **B3/B4**: implement the ports as async methods; no sync wrappers are needed. `context.service._context` imports `app.services.context`, but B4's module is `app.services.context_loader` (the snapshot already uses that one).

## Merged into `dga-next` (with P1-A and P1-B)

The merge applies the merge notes above. `make check` is green: 2734 passed.

- **Made async in P1's code:**
  - C8 in `context/service.py`: `learn_from_annotation`, `save_rule_change` (await `pattern_rules.*`).
  - C9 in `context/propagate.py`: `reevaluate_after_fact`, `on_fact_changed` and `_context`.
  - C10: `infer_hypotheses` and `_rejected_facts`.
  - C12: `suggest_savings_products`.
  - The test stand-ins, with `tests.builders.returning(value)` as the shared async loader.
  - `context/rules.py`, `inference.py`, `products.py`, `calendar_events.py` and `language.py` are pure and stay sync.
- **`_context`** now loads B4's real module, `app.services.context_loader`.
- **`on_annotation_changed`:**
  - The port keeps `(…, old: Decimal, new: Decimal)` and adds the optional keyword-only arguments `before`/`after: TxView`.
  - `apply_annotation` passes the transaction before and after the write.
  - `LazyEngine` hands danutu's E3 the two `TxView`s, which `reannotate_delta` reads for the purpose, the pot and the amount. When they are missing, it loads `after` through `transactions.get` and builds `before` from it with the old amount.
- **`recompute_plan` may return `None`** (no goal, E4):
  - The executor then returns `plan: null` and `forecast: null`, and skips `forecast_goal` (no `internal_error`).
  - `propagate.on_fact_changed` returns without a plan.
