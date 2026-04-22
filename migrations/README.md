Migrations are the source of truth for SQLite schema changes.

- Add new schema changes as numbered `NNNN_description.sql` files.
- `schema.sql` is retained briefly for historical reference and will be removed in a follow-up cleanup PR.
- The migration runner records applied versions in `schema_migrations` and marks legacy baseline versions for older user databases when the required columns already exist.
