import io
from typing import Optional

import fitz  # PyMuPDF


def parse_resume(file_bytes: bytes) -> str:
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    pages_text = []
    for page_num in range(doc.page_count):
        page = doc.load_page(page_num)
        text = page.get_text("text", sort=True)
        pages_text.append(text)
    doc.close()

    full_text = "\n".join(pages_text).strip()
    return full_text if full_text else ""
