"""Text extraction from supported document formats."""
from __future__ import annotations

import io

from app.core.exceptions import DocumentParseError, UnsupportedFileTypeError
from app.core.logging import get_logger

_logger = get_logger(__name__)


def _extract_txt(data: bytes) -> str:
    """Decode plain text / markdown, tolerating imperfect encodings."""
    for encoding in ("utf-8", "utf-16", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    # Last resort: never raise on stray bytes, replace them instead.
    return data.decode("utf-8", errors="replace")


def _extract_pdf(data: bytes) -> str:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(io.BytesIO(data))
        pages = [page.extract_text() or "" for page in reader.pages]
    except (PdfReadError, ValueError, OSError) as exc:
        raise DocumentParseError(f"Could not read PDF: {exc}") from exc
    return "\n\n".join(pages)


def _extract_docx(data: bytes) -> str:
    import docx
    from docx.opc.exceptions import PackageNotFoundError

    try:
        document = docx.Document(io.BytesIO(data))
    except (PackageNotFoundError, KeyError, ValueError) as exc:
        raise DocumentParseError(f"Could not read DOCX: {exc}") from exc
    return "\n\n".join(p.text for p in document.paragraphs)


_EXTRACTORS = {
    "txt": _extract_txt,
    "md": _extract_txt,
    "pdf": _extract_pdf,
    "docx": _extract_docx,
}


def extract_text(*, extension: str, data: bytes) -> str:
    """Extract plain text from ``data`` based on its file ``extension``.

    Args:
        extension: Lower-case extension without a leading dot.
        data: Raw file bytes.

    Returns:
        Extracted text (possibly empty if the document has no textual content).

    Raises:
        UnsupportedFileTypeError: If ``extension`` has no registered extractor.
        DocumentParseError: If the document is corrupt or unreadable.
    """
    extractor = _EXTRACTORS.get(extension.lower())
    if extractor is None:
        raise UnsupportedFileTypeError(f"No extractor for '.{extension}' files.")

    text = extractor(data)
    _logger.info("text_extracted", extension=extension, characters=len(text))
    return text
