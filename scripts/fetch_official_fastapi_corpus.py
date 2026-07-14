"""Fetch a pinned, public FastAPI documentation corpus for local RAG evaluation."""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "evals" / "corpora" / "fastapi-official-2026-07-14"
RAW_BASE_URL = "https://raw.githubusercontent.com/fastapi/fastapi/master/docs/en/docs/tutorial"
SOURCES = {
    "01-path-params.md": f"{RAW_BASE_URL}/path-params.md",
    "02-query-params.md": f"{RAW_BASE_URL}/query-params.md",
    "03-request-body.md": f"{RAW_BASE_URL}/body.md",
    "04-dependencies.md": f"{RAW_BASE_URL}/dependencies/index.md",
    "05-response-model.md": f"{RAW_BASE_URL}/response-model.md",
    "06-handling-errors.md": f"{RAW_BASE_URL}/handling-errors.md",
    "07-testing.md": f"{RAW_BASE_URL}/testing.md",
    "08-sql-databases.md": f"{RAW_BASE_URL}/sql-databases.md",
    "09-oauth2-jwt.md": f"{RAW_BASE_URL}/security/oauth2-jwt.md",
}


def fetch(url: str) -> bytes:
    completed = subprocess.run(
        ["curl", "--fail", "--location", "--silent", "--show-error", url],
        check=True,
        capture_output=True,
    )
    return completed.stdout


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    documents = []
    for filename, url in SOURCES.items():
        content = fetch(url)
        (OUTPUT_DIR / filename).write_bytes(content)
        documents.append(
            {
                "filename": filename,
                "source_url": url,
                "sha256": hashlib.sha256(content).hexdigest(),
                "bytes": len(content),
            }
        )

    manifest = {
        "dataset_name": "FastAPI official documentation corpus",
        "source_repository": "https://github.com/fastapi/fastapi",
        "fetched_at_utc": datetime.now(UTC).isoformat(),
        "documents": documents,
        "license_note": "Source content remains subject to the FastAPI project's license.",
    }
    (OUTPUT_DIR / "source-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Fetched {len(documents)} documents into {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
