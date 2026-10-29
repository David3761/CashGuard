"""CRUD services (B3). Contract: every function takes `db` and `user_id` and only touches that
user's rows (except products and merchants); another user's id → `DomainError("not_found", 404)`.
Reads return `app.domain` objects, never ORM rows. Invalid state changes →
`DomainError("invalid_transition", 409)`. Functions flush; the caller owns the commit.
The full list is pinned by tests/unit/test_service_contracts.py.
"""
