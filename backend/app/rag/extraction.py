"""File validation and text extraction for PDF, DOCX, TXT, CSV, XLSX and Markdown."""
import csv
import io
import re
import zipfile
from dataclasses import dataclass, field
from app.core.errors import bad_request

ALLOWED = {"pdf": "application/pdf", "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
           "txt": "text/plain", "csv": "text/csv", "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
           "md": "text/markdown", "markdown": "text/markdown"}
MAX_UNCOMPRESSED = 200 * 1024 * 1024


@dataclass
class Section:
    text: str
    page: int | None = None
    heading: str | None = None


@dataclass
class Extracted:
    sections: list[Section]
    page_count: int | None = None
    metadata: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    @property
    def full_text(self) -> str:
        return "\n\n".join(s.text for s in self.sections)


def file_type_of(filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED:
        raise bad_request(f"Unsupported file type '.{ext}'. Allowed: PDF, DOCX, TXT, CSV, XLSX, MD", "unsupported_file_type")
    return "md" if ext == "markdown" else ext


def validate_file(filename: str, data: bytes, max_mb: int) -> str:
    ft = file_type_of(filename)
    if not data:
        raise bad_request("File is empty", "empty_file")
    if len(data) > max_mb * 1024 * 1024:
        raise bad_request(f"File exceeds {max_mb} MB limit", "file_too_large")
    if ft == "pdf" and not data.startswith(b"%PDF"):
        raise bad_request("File content is not a valid PDF", "invalid_file")
    if ft in ("docx", "xlsx"):
        if not data.startswith(b"PK"):
            raise bad_request("File content is not a valid Office document", "invalid_file")
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                names = z.namelist()
                if "[Content_Types].xml" not in names:
                    raise bad_request("Malformed Office document", "invalid_file")
                if sum(i.file_size for i in z.infolist()) > MAX_UNCOMPRESSED:
                    raise bad_request("Archive expands beyond safe size (possible zip bomb)", "invalid_file")
                if any(n.lower().endswith(("vbaproject.bin",)) for n in names):
                    raise bad_request("Macro-enabled documents are not accepted", "invalid_file")
        except zipfile.BadZipFile:
            raise bad_request("Corrupt Office document", "invalid_file")
    if ft in ("txt", "md", "csv"):
        if b"\x00" in data[:4096]:
            raise bad_request("Binary content in a text file", "invalid_file")
        try:
            data.decode("utf-8")
        except UnicodeDecodeError:
            try:
                data.decode("latin-1")
            except UnicodeDecodeError:
                raise bad_request("Text file must be UTF-8 encoded", "invalid_file")
    return ft


def _decode(data: bytes) -> str:
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("latin-1")


def _ocr_pdf_page(data: bytes, page_no: int) -> str | None:
    """OCR adapter: used only when pytesseract + pdf2image + tesseract binary are installed (see DEPLOYMENT_GUIDE)."""
    try:
        import pytesseract  # type: ignore
        from pdf2image import convert_from_bytes  # type: ignore
    except ImportError:
        return None
    try:
        images = convert_from_bytes(data, first_page=page_no, last_page=page_no, dpi=200)
        return pytesseract.image_to_string(images[0]) if images else None
    except Exception:
        return None


def extract(file_type: str, data: bytes) -> Extracted:
    if file_type == "pdf":
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise bad_request("Encrypted PDFs are not supported", "invalid_file")
        sections, warnings, ocr_pages = [], [], 0
        for i, page in enumerate(reader.pages, start=1):
            txt = (page.extract_text() or "").strip()
            if len(txt) < 20:
                ocr = _ocr_pdf_page(data, i)
                if ocr and ocr.strip():
                    txt, ocr_pages = ocr.strip(), ocr_pages + 1
                elif not txt:
                    warnings.append(f"Page {i} has no extractable text (scanned?). OCR engine not installed.")
                    continue
            sections.append(Section(text=txt, page=i))
        meta = {k.strip("/"): str(v) for k, v in (reader.metadata or {}).items()} if reader.metadata else {}
        meta["ocr_pages"] = ocr_pages
        return Extracted(sections=sections, page_count=len(reader.pages), metadata=meta, warnings=warnings)
    if file_type == "docx":
        import docx
        d = docx.Document(io.BytesIO(data))
        sections, heading, buf = [], None, []
        for p in d.paragraphs:
            if p.style is not None and p.style.name.lower().startswith("heading") and p.text.strip():
                if buf:
                    sections.append(Section(text="\n".join(buf), heading=heading))
                heading, buf = p.text.strip(), []
            elif p.text.strip():
                buf.append(p.text.strip())
        if buf:
            sections.append(Section(text="\n".join(buf), heading=heading))
        for ti, table in enumerate(d.tables):
            rows = [" | ".join(c.text.strip() for c in r.cells) for r in table.rows]
            if rows:
                sections.append(Section(text="\n".join(rows), heading=f"Table {ti + 1}"))
        cp = d.core_properties
        return Extracted(sections=sections, metadata={"author": cp.author or "", "title": cp.title or ""})
    if file_type == "md":
        text = _decode(data)
        sections, heading, buf = [], None, []
        for line in text.splitlines():
            m = re.match(r"^(#{1,6})\s+(.*)", line)
            if m:
                if "".join(buf).strip():
                    sections.append(Section(text="\n".join(buf).strip(), heading=heading))
                heading, buf = m.group(2).strip(), []
            else:
                buf.append(line)
        if "".join(buf).strip():
            sections.append(Section(text="\n".join(buf).strip(), heading=heading))
        return Extracted(sections=sections)
    if file_type == "txt":
        return Extracted(sections=[Section(text=_decode(data))])
    if file_type == "csv":
        text = _decode(data)
        rows = list(csv.reader(io.StringIO(text)))
        return _tabular_sections("Sheet1", rows)
    if file_type == "xlsx":
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        ex = Extracted(sections=[], metadata={"sheets": wb.sheetnames})
        for ws in wb.worksheets:
            rows = [["" if v is None else str(v) for v in r] for r in ws.iter_rows(values_only=True)]
            ex.sections.extend(_tabular_sections(ws.title, rows).sections)
        return ex
    raise bad_request("Unsupported file type")


def _tabular_sections(sheet: str, rows: list[list[str]]) -> Extracted:
    rows = [r for r in rows if any(c.strip() for c in r)]
    if not rows:
        return Extracted(sections=[])
    header, body = rows[0], rows[1:]
    sections = []
    for i in range(0, len(body), 25):  # 25 rows per section, each row rendered as "col: value" for retrievability
        lines = ["; ".join(f"{h}: {v}" for h, v in zip(header, r) if str(v).strip()) for r in body[i:i + 25]]
        sections.append(Section(text="\n".join(lines), heading=f"{sheet} rows {i + 2}-{i + 1 + len(body[i:i + 25])}"))
    return Extracted(sections=sections, metadata={"columns": header, "rows": len(body)})
