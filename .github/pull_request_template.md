## What and why

<!-- Task ID (e.g. [C6]) and what this change does, in 2-5 lines. Link the step report if there is one. -->

## How it's tested

<!-- New/changed tests and the categories they cover (backend/docs/how-we-work.md §2). -->

## Checklist

- [ ] `cd backend && make check` is green (paste the summary line), and/or `flutter analyze` + `flutter test` in `mobile/`
- [ ] Tests were red for the right reason before the fix
- [ ] No secrets, `.env` files or real customer data
- [ ] Contract change (API, DB schema, event, tool)? The arch doc and `DGAREADME1.md` are updated
