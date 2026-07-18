import fitz  # PyMuPDF
from app.core.errors import AppError


def parse_pdf(filepath: str, max_pages: int, truncate_pages: int) -> tuple[list[dict], int]:
    """Extract text per page from a PDF. Returns (pages, page_count_processed).

    Each page dict: {page_number, text, avg_font_size}
    """
    doc = fitz.open(filepath)
    total_pages = doc.page_count

    if total_pages < 2:
        doc.close()
        raise AppError(detail="PDF must be at least 2 pages.", code="DOCUMENT_TOO_SHORT", status=400)

    pages_to_process = min(total_pages, truncate_pages) if total_pages > max_pages else total_pages

    pages = []
    total_chars = 0

    for i in range(pages_to_process):
        page = doc[i]
        blocks = page.get_text("dict")["blocks"]

        text_lines = []
        font_sizes = []

        for block in blocks:
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                size_sum = 0
                span_count = 0
                line_text_parts = []
                for span in line.get("spans", []):
                    size_sum += span["size"]
                    span_count += 1
                    line_text_parts.append(span["text"])
                if span_count > 0:
                    avg_size = size_sum / span_count
                    font_sizes.append(avg_size)
                    text_lines.append("".join(line_text_parts))

        page_text = "\n".join(text_lines)
        total_chars += len(page_text)

        # Weighted average font size for the page
        avg_font = sum(font_sizes) / len(font_sizes) if font_sizes else 0

        pages.append({
            "page_number": i + 1,
            "text": page_text,
            "avg_font_size": avg_font,
            "font_sizes": font_sizes,
        })

    doc.close()

    # Check for scanned PDF
    avg_chars_per_page = total_chars / pages_to_process if pages_to_process else 0
    if avg_chars_per_page < 50:
        raise AppError(
            detail="PDF appears to be scanned (too little extractable text).",
            code="DOCUMENT_IS_SCANNED",
            status=422,
        )

    return pages, pages_to_process


def detect_headings(pages: list[dict]) -> None:
    """Tag lines whose font size is in the top tier as chapter_hint on each page."""
    all_sizes = []
    for page in pages:
        all_sizes.extend(page["font_sizes"])

    if not all_sizes:
        return

    # Top tier = sizes within 10% of the max size
    top_tier = max(all_sizes)
    threshold = top_tier * 0.9

    for page in pages:
        hints = []
        blocks = page["text"].split("\n")
        sizes = page["font_sizes"]
        for i, line in enumerate(blocks):
            if i < len(sizes) and sizes[i] >= threshold and len(line.strip()) > 2:
                hints.append(line.strip())
        page["chapter_hints"] = hints
