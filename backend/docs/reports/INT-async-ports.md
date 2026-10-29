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
