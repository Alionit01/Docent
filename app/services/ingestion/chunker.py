import tiktoken
from app.core.ids import generate_id

_tokenizer = tiktoken.get_encoding("cl100k_base")

CHUNK_SIZE = 800
OVERLAP = 100


def chunk_pages(pages: list[dict]) -> list[dict]:
    """Split cleaned pages into overlapping chunks. Returns list of chunk dicts."""
    chunks = []

    for page in pages:
        text = page["text"]
        if len(text.strip()) < 20:
            continue

        page_num = page["page_number"]
        chapter_hint = page["chapter_hints"][0] if page.get("chapter_hints") else None

        tokens = _tokenizer.encode(text)
        token_count = len(tokens)

        if token_count <= CHUNK_SIZE:
            content = _tokenizer.decode(tokens)
            chunks.append({
                "id": generate_id("chk"),
                "content": content,
                "page_number": page_num,
                "chapter_hint": chapter_hint,
                "token_count": token_count,
            })
            continue

        # Sliding window
        start = 0
        while start < token_count:
            end = min(start + CHUNK_SIZE, token_count)
            chunk_tokens = tokens[start:end]
            content = _tokenizer.decode(chunk_tokens)

            # Try to split at natural boundaries (newlines) near the middle
            if end < token_count and len(chunk_tokens) >= CHUNK_SIZE:
                half = len(content) // 2
                nl = content.rfind("\n", half, len(content))
                if nl != -1 and nl < len(content) - 20:
                    content = content[:nl].strip()

            chunks.append({
                "id": generate_id("chk"),
                "content": content,
                "page_number": page_num,
                "chapter_hint": chapter_hint,
                "token_count": len(chunk_tokens),
            })

            start += CHUNK_SIZE - OVERLAP
            if start >= token_count:
                break

    return chunks
