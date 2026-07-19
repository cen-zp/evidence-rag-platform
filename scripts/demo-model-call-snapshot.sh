#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
project_dir="$(cd -- "${script_dir}/.." && pwd)"

cd "${project_dir}"

docker compose exec -T api uv run --no-sync python -c '
from sqlalchemy import func, select

from app.db.session import get_session_factory
from app.models import ModelCall

factory = get_session_factory()
session = factory()
try:
    count = session.scalar(select(func.count(ModelCall.id))) or 0
    latest = session.scalar(select(func.max(ModelCall.created_at)))
finally:
    session.close()

print(f"model_call_count={count}")
print(f"latest_model_call_at={latest.isoformat() if latest else None}")
'
