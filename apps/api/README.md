# Evidence RAG API

FastAPI service with the initial model-call path and minimum knowledge-base persistence schema.

## Database migrations

From `apps/api`, apply the current migration to the PostgreSQL configured by the project-root `.env`:

```bash
uv run python -m alembic upgrade head
```

Inspect the migration SQL without connecting to a database:

```bash
uv run python -m alembic upgrade head --sql
```

The current schema and PostgreSQL/Qdrant ID contract are documented in `docs/data-model.md`.
