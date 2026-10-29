# Tests

```bash
make db-up                                   # Postgres for tests (port 5435), once
make test                                    # everything except live (unit + db + api + ws)
uv run pytest tests/unit -q                  # pure, no DB, milliseconds
uv run pytest -m db -q                       # needs Postgres
uv run pytest -m api -q                      # HTTP endpoints
uv run pytest -m ws -q                       # WebSocket
uv run pytest -m live tests/eval             # real Claude: costs money, on purpose only
```

The folder sets the marker: `tests/db/*` → `db`, `tests/api/*` → `api`, `tests/ws/*` → `ws`
(see `conftest.py`). Every test runs with the app clock frozen at **2026-06-15 12:00 Bucharest**
(the `fixed_clock` fixture, automatic); call `clock.set_clock(FixedClock(...))` for another time.

## Building blocks

| Module | What |
|---|---|
| `tests/builders.py` | pure domain objects: `tx()`, `history()`, `fact()`, `signature()`, `rule()`, `ctx()`, and the personas `matei_ctx()`, `andrei_ctx()`, `bianca_ctx()`, `ioana_ctx()` (unit tests of the engine and the context layer) |
| `tests/factories.py` | DB rows: `await factories.user(db)`, `goal`, `transaction`, `everything` (one row in every per-user table) |
| `tests/fixtures/*.py` | the fixtures below (loaded by `conftest.py`) |

## Fixtures

### `db`: a session rolled back after the test (default for db tests)

```python
async def test_goal_is_active_by_default(db):
    user = await factories.user(db)
    goal = await factories.goal(db, user.id)
    assert goal.status == "active"
```
Even `await db.commit()` stays inside the test (it commits a SAVEPOINT).

### `db_committed`: real commits, everything truncated after

For code that opens its own sessions (the pipeline, background agent runs, locks, concurrency):
the app's `unit_of_work()` / `get_db()` point at the test DB during the test.

```python
async def test_pipeline_resolves(db_committed):
    user = await factories.user(db_committed)
    await db_committed.commit()
    await process_user(user.id, "sim")         # opens its own unit_of_work()
```

### `make_token`, `test_jwks`: tokens signed with a test key

```python
async def test_expired(make_token, test_jwks):
    with pytest.raises(DomainError):
        await verify_token(make_token(exp_in=-31))   # 30 s leeway
```
`make_token(sub=…, roles=("internal",), exp_in=300, iss=…, azp="savings-frontend", aud=None,
nbf_in=None, kid="test")`. Broken tokens for security tests: `tests.fixtures.auth.unsigned_token`
(`alg: none`) and `hs256_with_public_key` (algorithm confusion).

### `client`, `as_user`: HTTP

```python
async def test_me(as_user, db):
    user = await factories.user(db)
    r = await as_user(user).get("/me")             # base URL is http://test/api
    assert r.status_code == 200
```
The app's `get_db` yields the test's `db` session, so rows you add in the test are visible to
the endpoint without committing. `as_user(user, roles=(), **make_token_kwargs)` takes a users
row or a `sub` string.

### `ws_connect`: WebSocket

```python
def test_push(ws_connect):
    with ws_connect("a0000000-0000-4000-8000-000000000001") as ws:   # /ws?token=…
        event = ws.receive_json()
```
Runs the app in Starlette's TestClient (another thread and event loop): use committed data
(`db_committed`), not the rolled-back `db` session.

## Conventions (how-we-work §7)

- Name: `test_<unit>_<behaviour>_<condition>`.
- Tests first; show them red for the right reason before implementing.
- No `sleep`, no `datetime.now()`, every random generator seeded.
- Real Claude only behind `-m live`; everything else uses `FakeLLM` (A1).
