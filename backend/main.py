"""
backend/main.py

FastAPI application: analyze -> review -> clone-redact.

Run:  uvicorn backend.main:app --reload --port 8000
"""

from __future__ import annotations

import base64
import json
import logging
import os
import threading
import uuid
from collections import Counter
from contextlib import asynccontextmanager
from importlib import metadata
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from backend.engine.ingestor import DocumentIngestor, IngestionError, UnsupportedFormatError
from backend.engine.redactor import CIADocumentRedactor, RedactionError, sha256_hex

logger = logging.getLogger("cia.api")

ALLOWED_EXTS = {".txt", ".pdf", ".png", ".jpg", ".jpeg"}
MAX_UPLOAD_BYTES = 25 * 1024 * 1024
MAX_SESSIONS = 25
FRONTEND_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]

# In-memory demo session cache: session_id -> {filename, file_type, bytes, sha256_original, entities, ...}
DOCUMENT_STORE: Dict[str, dict] = {}
_STORE_LOCK = threading.Lock()

_ingestor: Optional[DocumentIngestor] = None
_ingestor_lock = threading.Lock()
_redactor = CIADocumentRedactor()


def get_ingestor() -> DocumentIngestor:
    global _ingestor
    with _ingestor_lock:
        if _ingestor is None:
            _ingestor = DocumentIngestor()
        return _ingestor


@asynccontextmanager
async def lifespan(_: FastAPI):
    get_ingestor()  # warm up Presidio / spaCy / OCR wiring so the first request is fast
    yield


app = FastAPI(title="CIA Zero-Leak Redaction API", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ----------------------------------------------------------------------------
# Schemas
# ----------------------------------------------------------------------------
class BoundingBoxModel(BaseModel):
    x0: float
    y0: float
    x1: float
    y1: float


class EntityModel(BaseModel):
    id: str
    entity_type: str
    text: str
    score: Optional[float] = None
    page_number: int = 1
    line_number: int
    start_char: int
    end_char: int
    bbox: Optional[BoundingBoxModel] = None
    selected_for_redaction: bool = True


class TextLineModel(BaseModel):
    line_number: int
    text: str
    bbox: Optional[BoundingBoxModel] = None


class PageModel(BaseModel):
    page_number: int
    width: Optional[float] = None
    height: Optional[float] = None
    source: str
    preview_b64: Optional[str] = None     # base64 PNG, no data-URI prefix
    raw_text_lines: List[TextLineModel] = Field(default_factory=list)


class AnalyzeResponse(BaseModel):
    session_id: str
    filename: str
    file_type: str
    sha256_original: str
    page_count: int
    pages: List[PageModel]
    entities: List[EntityModel]
    entity_counts: Dict[str, int]


class EntitySelection(BaseModel):
    id: str
    selected_for_redaction: bool = True


class CustomBoxModel(BaseModel):
    page_number: int = 1
    bbox: BoundingBoxModel


class RedactCloneRequest(BaseModel):
    session_id: str
    mode: Literal["cia_blackout", "partial_mask", "entity_tag"] = "cia_blackout"
    add_declassified_stamp: bool = False
    # Per-entity selection state from the review UI. Entities not listed default to
    # SELECTED (fail-safe: redact rather than leak).
    entities: List[EntitySelection] = Field(default_factory=list)
    # User-drawn manual boxes (image / PDF only), normalized [0, 1] page coordinates.
    custom_boxes: List[CustomBoxModel] = Field(default_factory=list, max_length=500)


class RedactCloneResponse(BaseModel):
    session_id: str
    output_filename: str
    mime_type: str
    file_b64: str
    sha256_original: str
    sha256_redacted: str
    entity_counts: Dict[str, int]
    total_redacted: int
    certificate: Dict[str, Any]


class LicenseEntry(BaseModel):
    name: str
    version: Optional[str] = None
    license: str
    homepage: Optional[str] = None
    purpose: Optional[str] = None


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------
def _attr(obj: Any, *names: str, default: Any = None) -> Any:
    for n in names:
        v = obj.get(n) if isinstance(obj, dict) else getattr(obj, n, None)
        if v is not None:
            return v
    return default


def _bbox_dict(bbox: Any) -> Optional[dict]:
    if bbox is None:
        return None
    return {k: float(getattr(bbox, k)) for k in ("x0", "y0", "x1", "y1")}


def _evict_if_needed() -> None:
    while len(DOCUMENT_STORE) > MAX_SESSIONS:
        DOCUMENT_STORE.pop(next(iter(DOCUMENT_STORE)))   # oldest first (insertion order)


# ----------------------------------------------------------------------------
# Endpoints
# ----------------------------------------------------------------------------
@app.post("/api/v1/analyze", response_model=AnalyzeResponse)
def analyze(file: UploadFile = File(...)) -> AnalyzeResponse:
    # Sync endpoint on purpose: OCR / PDF rendering are CPU-bound, FastAPI runs this in a threadpool.
    filename = os.path.basename(file.filename or "upload")
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTS:
        raise HTTPException(400, f"Unsupported file type '{ext}'. Allowed: {sorted(ALLOWED_EXTS)}")

    data = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"File exceeds {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit")
    if not data:
        raise HTTPException(400, "Empty file")

    sha_original = sha256_hex(data)

    try:
        result = get_ingestor().ingest(filename, data)
    except UnsupportedFormatError as exc:
        raise HTTPException(400, str(exc)) from exc
    except IngestionError as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:
        logger.exception("Ingestion failed")
        raise HTTPException(500, f"{type(exc).__name__}: {exc}") from exc

    entities: List[dict] = []
    for finding in result.findings:
        ent = finding.entity
        score = _attr(ent, "score", "confidence")
        entities.append({
            "id": f"ent_{len(entities):04d}",
            "entity_type": str(_attr(ent, "entity_type", "type", default="UNKNOWN")),
            "text": finding.text,
            "score": float(score) if score is not None else None,
            "page_number": finding.page_number,
            "line_number": finding.line_number,
            "start_char": finding.start_char,
            "end_char": finding.end_char,
            "bbox": _bbox_dict(finding.bbox),
            "selected_for_redaction": True,
        })

    pages = [
        {
            "page_number": p.page_number,
            "width": p.width,
            "height": p.height,
            "source": p.source,
            "preview_b64": p.preview_b64,
            "raw_text_lines": [
                {"line_number": ln.line_number, "text": ln.text, "bbox": _bbox_dict(ln.bbox)}
                for ln in p.raw_text_lines
            ],
        }
        for p in result.pages
    ]

    session_id = uuid.uuid4().hex
    with _STORE_LOCK:
        DOCUMENT_STORE[session_id] = {
            "filename": filename,
            "file_type": result.file_type,
            "bytes": data,
            "sha256_original": sha_original,
            "entities": entities,
            "page_count": len(result.pages),
        }
        _evict_if_needed()

    return AnalyzeResponse(
        session_id=session_id,
        filename=filename,
        file_type=result.file_type,
        sha256_original=sha_original,
        page_count=len(result.pages),
        pages=pages,
        entities=entities,
        entity_counts=dict(Counter(e["entity_type"] for e in entities)),
    )


@app.post("/api/v1/clone-redact", response_model=RedactCloneResponse)
def clone_redact(req: RedactCloneRequest) -> RedactCloneResponse:
    with _STORE_LOCK:
        session = DOCUMENT_STORE.get(req.session_id)
    if session is None:
        raise HTTPException(404, "Session not found or expired. Please re-upload the document.")

    # Offsets / boxes always come from the server-side analysis, never from the client.
    selection = {s.id: s.selected_for_redaction for s in req.entities}
    entities = [
        {**e, "selected_for_redaction": selection.get(e["id"], True)}
        for e in session["entities"]
    ]

    if session["file_type"] != "txt":
        page_count = session["page_count"]
        for i, box in enumerate(req.custom_boxes):
            if 1 <= box.page_number <= page_count:
                b = box.bbox
                entities.append({
                    "id": f"custom_{i}", "entity_type": "CUSTOM_BOX",
                    "page_number": box.page_number, "line_number": 0,
                    "start_char": 0, "end_char": 0,
                    "bbox": {"x0": b.x0, "y0": b.y0, "x1": b.x1, "y1": b.y1},
                    "selected_for_redaction": True,
                })

    try:
        result = _redactor.redact(
            filename=session["filename"],
            file_type=session["file_type"],
            source_bytes=session["bytes"],
            entities=entities,
            mode=req.mode,
            add_declassified_stamp=req.add_declassified_stamp,
            sha256_original=session["sha256_original"],
        )
    except RedactionError as exc:
        raise HTTPException(422, str(exc)) from exc

    return RedactCloneResponse(
        session_id=req.session_id,
        output_filename=result.output_filename,
        mime_type=result.mime_type,
        file_b64=base64.b64encode(result.file_bytes).decode("ascii"),
        sha256_original=session["sha256_original"],
        sha256_redacted=result.sha256_redacted,
        entity_counts=result.entity_counts,
        total_redacted=sum(result.entity_counts.values()),
        certificate=result.certificate,
    )


# --- Open-source disclosure ---------------------------------------------------------
# (distribution name, display name, license, homepage, purpose)
_COMPONENTS = [
    ("fastapi", "FastAPI", "MIT", "https://fastapi.tiangolo.com", "REST API framework"),
    ("uvicorn", "Uvicorn", "BSD-3-Clause", "https://www.uvicorn.org", "ASGI server"),
    ("pydantic", "Pydantic", "MIT", "https://docs.pydantic.dev", "Request/response validation"),
    ("presidio-analyzer", "Microsoft Presidio Analyzer", "MIT",
     "https://microsoft.github.io/presidio", "PII entity detection"),
    ("spacy", "spaCy", "MIT", "https://spacy.io", "NLP pipeline for Presidio"),
    ("rapidocr-onnxruntime", "RapidOCR (ONNX Runtime)", "Apache-2.0",
     "https://github.com/RapidAI/RapidOCR", "Optical character recognition"),
    ("onnxruntime", "ONNX Runtime", "MIT", "https://onnxruntime.ai", "OCR model inference"),
    ("opencv-python", "OpenCV", "Apache-2.0", "https://opencv.org", "Image decoding & redaction drawing"),
    ("pdfplumber", "pdfplumber", "MIT", "https://github.com/jsvine/pdfplumber", "Digital PDF text/char geometry"),
    ("pypdfium2", "pypdfium2 / PDFium", "Apache-2.0 OR BSD-3-Clause",
     "https://github.com/pypdfium2-team/pypdfium2", "200-DPI PDF page rendering"),
    ("pillow", "Pillow", "MIT-CMU (HPND)", "https://python-pillow.org", "Image / flattened PDF export"),
    ("numpy", "NumPy", "BSD-3-Clause", "https://numpy.org", "Bitmap arrays"),
]


def _load_licenses() -> List[LicenseEntry]:
    """Prefer backend/data/licenses.json (curated list); otherwise build from the table above."""
    curated = Path(__file__).parent / "data" / "licenses.json"
    if curated.is_file():
        try:
            raw = json.loads(curated.read_text(encoding="utf-8"))
            return [LicenseEntry(**item) for item in raw]
        except Exception:
            logger.exception("Could not parse %s; falling back to built-in list", curated)

    entries: List[LicenseEntry] = []
    for dist, name, lic, home, purpose in _COMPONENTS:
        try:
            version: Optional[str] = metadata.version(dist)
        except metadata.PackageNotFoundError:
            version = None
        entries.append(LicenseEntry(name=name, version=version, license=lic,
                                    homepage=home, purpose=purpose))
    return entries


@app.get("/api/v1/licenses", response_model=List[LicenseEntry])
def licenses() -> List[LicenseEntry]:
    return _load_licenses()


@app.get("/api/v1/health")
def health() -> dict:
    return {"status": "ok", "sessions": len(DOCUMENT_STORE)}
