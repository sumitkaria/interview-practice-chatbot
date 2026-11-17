"""Read job descriptions and résumés from common file types."""

from __future__ import annotations

import io
import re
from pathlib import Path

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_TEXT_CHARS = 60_000
MAX_FILES = 8
MAX_PDF_PAGES = 30

TEXT_EXTENSIONS = {".txt", ".md", ".markdown", ".csv", ".text", ".log"}
HTML_EXTENSIONS = {".html", ".htm"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}

UPLOAD_TYPES = [
    "pdf",
    "docx",
    "txt",
    "md",
    "rtf",
    "html",
    "htm",
    "csv",
    "png",
    "jpg",
    "jpeg",
]


def tidy(text: str) -> str:
    text = text.replace("\x00", "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def truncate(text: str) -> str:
    cleaned = tidy(text)
    if len(cleaned) <= MAX_TEXT_CHARS:
        return cleaned
    return cleaned[:MAX_TEXT_CHARS].rstrip() + "\n\n[Text was shortened to fit the interview session.]"


def decode_text(data: bytes) -> str:
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")


def _extension(name: str) -> str:
    return Path(name).suffix.lower()


def _image_mime(extension: str) -> str:
    if extension == ".png":
        return "image/png"
    return "image/jpeg"


def extract_named_bytes(name: str, data: bytes, image_reader) -> str:
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError(f"{name} is larger than 10 MB.")
    extension = _extension(name)
    if extension == ".doc":
        raise ValueError(f"{name} could not be read. Paste the text instead.")
    if extension == ".pdf":
        text = _read_pdf(data)
    elif extension == ".docx":
        text = _read_docx(data)
    elif extension == ".rtf":
        text = _read_rtf(data)
    elif extension in HTML_EXTENSIONS:
        text = _read_html(data)
    elif extension in TEXT_EXTENSIONS:
        text = decode_text(data)
    elif extension in IMAGE_EXTENSIONS:
        if image_reader is None:
            raise ValueError(
                f"{name} is an image. Paste the text instead."
            )
        text = image_reader(data, _image_mime(extension))
    else:
        raise ValueError(f"{name} could not be read. Paste the text instead.")
    cleaned = tidy(text)
    if not cleaned:
        raise ValueError(
            f"No text could be read from {name}. Paste the text instead."
        )
    return cleaned


def extract_uploads(files, image_reader) -> tuple[str, str]:
    items = list(files or [])
    if not items:
        raise ValueError("Choose a file to upload.")
    if len(items) > MAX_FILES:
        raise ValueError("Upload up to 8 files at a time.")
    parts: list[str] = []
    names: list[str] = []
    multiple = len(items) > 1
    for item in items:
        name = Path(getattr(item, "name", "upload")).name
        data = item.getvalue()
        text = extract_named_bytes(name, data, image_reader)
        parts.append(f"--- {name} ---\n{text}" if multiple else text)
        names.append(name)
    source = ", ".join(names)
    if len(source) > 280:
        source = source[:277] + "..."
    return truncate("\n\n".join(parts)), source


def _read_pdf(data: bytes) -> str:
    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(data))
        if len(reader.pages) > MAX_PDF_PAGES:
            raise ValueError(
                f"That PDF has more than {MAX_PDF_PAGES} pages. Paste the part you want practiced."
            )
        pages = [(page.extract_text() or "") for page in reader.pages]
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("That file could not be read. Paste the text instead.") from exc
    return "\n\n".join(pages)


def _read_docx(data: bytes) -> str:
    from docx import Document

    try:
        document = Document(io.BytesIO(data))
    except Exception as exc:
        raise ValueError("That file could not be read. Paste the text instead.") from exc
    lines = [paragraph.text for paragraph in document.paragraphs]
    for table in document.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells]
            lines.append(" | ".join(cell for cell in cells if cell))
    return "\n".join(lines)


def _read_rtf(data: bytes) -> str:
    from striprtf.striprtf import rtf_to_text

    try:
        return rtf_to_text(decode_text(data))
    except Exception as exc:
        raise ValueError("That file could not be read. Paste the text instead.") from exc


def _read_html(data: bytes) -> str:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(data, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    return soup.get_text("\n")
