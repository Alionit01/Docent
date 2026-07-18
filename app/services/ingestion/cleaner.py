import re


def clean_pages(pages: list[dict]) -> list[dict]:
    """Remove headers/footers, de-hyphenate, normalize whitespace."""
    # Collect all lines across all pages to detect repeated lines (headers/footers)
    line_counts: dict[str, int] = {}
    for page in pages:
        for line in page["text"].split("\n"):
            stripped = line.strip()
            if stripped:
                line_counts[stripped] = line_counts.get(stripped, 0) + 1

    total_pages = len(pages)
    # Lines appearing on >70% of pages are headers/footers
    threshold = int(total_pages * 0.7)
    repeated_lines = {line for line, count in line_counts.items() if count > threshold}

    cleaned = []
    for page in pages:
        lines = page["text"].split("\n")
        kept_lines = []
        for line in lines:
            stripped = line.strip()
            if stripped in repeated_lines:
                continue
            kept_lines.append(stripped)

        text = "\n".join(kept_lines)

        # De-hyphenate: "some-\nthing" → "something"
        text = re.sub(r"(\w+)-\n(\w+)", r"\1\2", text)

        # Normalize whitespace
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = text.strip()

        cleaned.append({
            "page_number": page["page_number"],
            "text": text,
            "chapter_hints": page.get("chapter_hints", []),
        })

    return cleaned
