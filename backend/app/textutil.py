"""Turn an uploaded document (text/scanned PDF, image, DOCX, saved email, text, HTML) into plain text."""
import email
import email.policy
import html as _html
import io
import re

import pymupdf
import pytesseract
from PIL import Image
from docx import Document

MIN_CHARS_PER_PAGE = 80
MAX_OCR_PAGES = 10  # a PDF page with less text than MIN_CHARS_PER_PAGE is treated as scanned


def _ocr_image(img: Image.Image) -> str:
    return pytesseract.image_to_string(img)


def extract_text(filename: str, data: bytes, on_progress=None):
    """Returns (text, notes). notes lists things the user should know (e.g. OCR used)."""
    name = filename.lower()
    notes = []
    if name.endswith(".pdf"):
        doc = pymupdf.open(stream=data, filetype="pdf")
        total = len(doc)
        parts = []
        ocr_pages = 0
        for idx, page in enumerate(doc, 1):
            t = page.get_text()
            if len(t.strip()) < MIN_CHARS_PER_PAGE and ocr_pages < MAX_OCR_PAGES:
                if on_progress:
                    on_progress(idx, total, True)
                pix = page.get_pixmap(dpi=150)
                img = Image.open(io.BytesIO(pix.tobytes("png")))
                t = _ocr_image(img)
                ocr_pages += 1
            elif on_progress:
                on_progress(idx, total, False)
            parts.append(t)
        if ocr_pages:
            notes.append(f"{filename}: {ocr_pages} page(s) read with OCR, so check extracted values carefully.")
        skipped = sum(1 for t in parts if len(t.strip()) < MIN_CHARS_PER_PAGE) - ocr_pages
        if skipped > 0 and ocr_pages >= MAX_OCR_PAGES:
            notes.append(f"{filename}: only the first {MAX_OCR_PAGES} scanned pages were read; later pages were skipped.")
        return "\n".join(parts), notes
    if name.endswith(".docx"):
        d = Document(io.BytesIO(data))
        lines = [p.text for p in d.paragraphs]
        for t in d.tables:
            for r in t.rows:
                lines.append(" | ".join(c.text for c in r.cells))
        return "\n".join(lines), notes
    if name.endswith((".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp")):
        notes.append(f"{filename}: read with OCR, so check extracted values carefully.")
        return _ocr_image(Image.open(io.BytesIO(data))), notes
    if name.endswith(".eml"):
        return _read_eml(data), notes
    if name.endswith((".txt", ".md", ".csv")):
        return _decode(data), notes
    if name.endswith((".html", ".htm")):
        return _html_to_text(_decode(data)), notes
    if name.endswith(".msg"):
        raise ValueError(f"{filename}: Outlook .msg files can't be read. Open the email, choose Print > Save as PDF, "
                         "or save it as .eml, and upload that instead.")
    raise ValueError(f"Unsupported file type: {filename}")


def _decode(data: bytes) -> str:
    for enc in ("utf-8-sig", "utf-16", "cp1252", "latin-1"):
        try:
            return data.decode(enc)
        except (UnicodeDecodeError, UnicodeError):
            continue
    return data.decode("utf-8", errors="replace")


def _html_to_text(h: str) -> str:
    h = re.sub(r"(?is)<(script|style).*?</\1>", " ", h)
    h = re.sub(r"(?i)<br\s*/?>|</(p|div|tr|li|h[1-6]|table)>", "\n", h)
    h = re.sub(r"(?i)</t[dh]>", " | ", h)
    h = re.sub(r"<[^>]+>", " ", h)
    h = _html.unescape(h)
    return re.sub(r"[ \t]+", " ", re.sub(r"\n\s*\n+", "\n\n", h)).strip()


def _read_eml(data: bytes) -> str:
    msg = email.message_from_bytes(data, policy=email.policy.default)
    head = [f"{k}: {msg[k]}" for k in ("From", "To", "Cc", "Date", "Subject") if msg[k]]
    body = msg.get_body(preferencelist=("plain", "html"))
    text = ""
    if body is not None:
        text = body.get_content()
        if body.get_content_type() == "text/html":
            text = _html_to_text(text)
    names = [p.get_filename() for p in msg.iter_attachments() if p.get_filename()]
    if names:
        head.append("Attachments: " + ", ".join(names))
    return "\n".join(head) + "\n\n" + text


def normalise(s: str) -> str:
    """Collapse whitespace/hyphenation so quotes can be matched against source text."""
    s = s.replace("­", "").replace("-\n", "")
    s = re.sub(r"[‘’]", "'", s)
    s = re.sub(r"[“”]", '"', s)
    return re.sub(r"\s+", " ", s).strip().lower()


def normalise_loose(s: str) -> str:
    """Letters and digits only. Used to check a quote really comes from the document even when OCR or
    line-wrapping changed spaces, hyphens or punctuation. It cannot make an invented sentence match."""
    return re.sub(r"[^a-z0-9]+", "", normalise(s))
