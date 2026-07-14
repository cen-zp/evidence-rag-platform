from app.services.document_parsing import ParsedPage

CHUNK_SIZE = 800
CHUNK_OVERLAP = 120


def chunk_pages(pages: list[ParsedPage]) -> list[tuple[str, int | None, dict[str, int]]]:
    chunks: list[tuple[str, int | None, dict[str, int]]] = []
    for page in pages:
        text = "\n".join(line.strip() for line in page.text.splitlines() if line.strip())
        if not text:
            continue
        for start in _chunk_starts(text):
            content = text[start : start + CHUNK_SIZE]
            chunks.append((content, page.page_number, {"char_start": start}))
    return chunks


def _chunk_starts(text: str) -> list[int]:
    if len(text) <= CHUNK_SIZE:
        return [0]

    starts: list[int] = []
    start = 0
    while start < len(text):
        starts.append(start)
        end = start + CHUNK_SIZE
        if end >= len(text):
            break
        start = end - CHUNK_OVERLAP
    return starts
