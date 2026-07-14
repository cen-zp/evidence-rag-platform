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

## Document intake and processing

The M2-A endpoints accept Markdown and PDF uploads up to 10 MB and create `pending` document records. M2-B submits processing work to Redis/ARQ; run this in a separate terminal from `apps/api`:

```bash
uv run arq app.workers.document.WorkerSettings
```

The worker parses Markdown/PDF files, creates chunks, and writes the local vector baseline to Qdrant. It changes the document state to `ready` or `failed`; see [../../docs/document-intake.md](../../docs/document-intake.md) and [../../docs/document-processing.md](../../docs/document-processing.md) for the current boundary. The hash-vector baseline is only for local pipeline verification, not semantic-retrieval quality.
