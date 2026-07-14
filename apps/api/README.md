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

## Retrieval

`POST /api/knowledge-bases/{kb_id}/search` searches only the selected knowledge base and returns traceable chunk IDs, source text, file name, page number, and score. It uses both a Qdrant payload filter and a PostgreSQL `ready`-document check. See [../../docs/retrieval.md](../../docs/retrieval.md).

## Grounded chat

Pass `knowledge_base_id` with a `POST /api/chat` request to enable evidence-grounded generation. The server refuses without calling the model when no evidence is retrieved, and validates the model's structured citation IDs against the same retrieval result. See [../../docs/grounded-chat.md](../../docs/grounded-chat.md).
