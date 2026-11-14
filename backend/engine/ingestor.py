"""
backend/engine/ingestor.py

Multi-format document ingestion with sub-line bounding-box mapping.

Paths
-----
A. .txt                 -> UTF-8 decode, per-line PII detection, character offsets only.
B. .png/.jpg/.jpeg      -> OpenCV decode + RapidOCR, sub-line bbox interpolation.
C. .pdf                 -> pypdfium2 200-DPI render (preview + bitmap canvas), then
     C1. digital page   (> 10 native chars)  -> pdfplumber char-exact boxes
     C2. scanned page   (<= 10 native chars) -> RapidOCR on the rendered bitmap (Path B)

Extra detectors on bitmap pages (B, C2) and on rendered digital PDF pages:
  * ID-card layout rule: on pages that look like an ID card, the capitalised line directly
    above the DOB (or gender) line is the holder's name (plus its regional-script copy).
  * Face photos via an OpenCV Haar cascade (entity type FACE_PHOTO).

All bounding boxes are normalized to [0.0, 1.0] page coordinates, origin top-left.
"""

from __future__ import annotations

import base64
import inspect
import io
import logging
import os
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, List, Optional, Tuple

import cv2
import numpy as np

# --- Project imports ---------------------------------------------------------
from backend.engine.pii_detector import HybridPIIDetector
from backend.models.schemas import BoundingBox, DetectedEntity

logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------------
# Constants
# ----------------------------------------------------------------------------
PDF_RENDER_DPI = 200
PDF_RENDER_SCALE = PDF_RENDER_DPI / 72.0
DIGITAL_TEXT_MIN_CHARS = 10        # page.chars must exceed this to count as digital
BBOX_PAD_PX = 2.0                  # safety padding, in pixels
IMAGE_EXTS = {".png", ".jpg", ".jpeg"}

FACE_ENTITY_TYPE = "FACE_PHOTO"
_HAAR_FILE = "haarcascade_frontalface_default.xml"

# ID-card layout heuristics. No leading \b on the DOB cue: OCR often glues garbled
# regional-script characters directly onto "DOB", and CJK characters count as \w.
_DOB_CUE = re.compile(r"(?i)d\.?o\.?b(?![a-z])|date\s+of\s+birth")
_NAME_LINE = re.compile(r"^[A-Z][A-Za-z.'\-]*(?:\s+[A-Z][A-Za-z.'\-]*){0,3}$")
_NOT_NAME = re.compile(
    r"(?i)\b(?:government|india|aadhaar|aadhar|male|female|dob|issued|authority|unique|identification|gender|birth)\b"
)
_GENDER_LINE = re.compile(r"(?i)(?<![a-z])(?:female|male|transgender)(?![a-z])")
_ID_CARD_CUE = re.compile(r"(?i)government\s+of\s+india|aadhaa?r|uidai|unique\s+identification")


class IngestionError(Exception):
    """Raised when a document cannot be decoded or processed."""


class UnsupportedFormatError(IngestionError):
    """Raised for unsupported file extensions."""


# ----------------------------------------------------------------------------
# Result containers
# ----------------------------------------------------------------------------
@dataclass
class TextLine:
    line_number: int            # 1-based within the page
    text: str
    start_char: int = 0         # offset of the line text within itself (always 0..len)
    end_char: int = 0
    bbox: Optional[BoundingBox] = None   # normalized line box (OCR / digital PDF)
    ocr_conf: Optional[float] = None


@dataclass
class Finding:
    entity: Any                          # DetectedEntity
    page_number: int                     # 1-based
    line_number: int                     # 1-based within the page
    start_char: int                      # offsets inside that line's text
    end_char: int
    text: str
    bbox: Optional[BoundingBox] = None   # None for plain text (no geometry)


@dataclass
class PageResult:
    page_number: int
    width: Optional[float]               # pixels (images / scanned) or points (digital PDF)
    height: Optional[float]
    source: str                          # "text" | "image" | "pdf_digital" | "pdf_ocr"
    raw_text_lines: List[TextLine] = field(default_factory=list)
    findings: List[Finding] = field(default_factory=list)
    preview_b64: Optional[str] = None    # base64 PNG (no data-URI prefix)
    # Clean RGB bitmap canvas for the redactor (not serialized to the frontend).
    bitmap_rgb: Optional[np.ndarray] = field(default=None, repr=False)


@dataclass
class IngestionResult:
    filename: str
    file_type: str
    pages: List[PageResult] = field(default_factory=list)

    @property
    def findings(self) -> List[Finding]:
        return [f for p in self.pages for f in p.findings]


# ----------------------------------------------------------------------------
# Sub-line bounding box interpolation
# ----------------------------------------------------------------------------
def slice_sub_bbox(
    line_bbox: Tuple[float, float, float, float],
    line_text_len: int,
    start_char: int,
    end_char: int,
    page_w: float,
    page_h: float,
) -> BoundingBox:
    """
    Proportionally slice a full-line pixel bbox down to the span [start_char:end_char].

    line_bbox is (line_x0, line_y0, line_x1, line_y1) in pixels. A 2-pixel safety
    pad is applied, then coordinates are normalized by page size and clamped to [0, 1].
    """
    line_x0, line_y0, line_x1, line_y1 = line_bbox

    char_width = (line_x1 - line_x0) / max(line_text_len, 1)
    sub_x0 = line_x0 + (start_char * char_width)
    sub_x1 = line_x0 + (end_char * char_width)

    x0 = sub_x0 - BBOX_PAD_PX
    y0 = line_y0 - BBOX_PAD_PX
    x1 = sub_x1 + BBOX_PAD_PX
    y1 = line_y1 + BBOX_PAD_PX

    return _normalize_box(x0, y0, x1, y1, page_w, page_h)


def _clamp01(v: float) -> float:
    return 0.0 if v < 0.0 else 1.0 if v > 1.0 else float(v)


def _normalize_box(
    x0: float, y0: float, x1: float, y1: float, page_w: float, page_h: float
) -> BoundingBox:
    pw = max(float(page_w), 1e-9)
    ph = max(float(page_h), 1e-9)
    nx0, nx1 = sorted((_clamp01(x0 / pw), _clamp01(x1 / pw)))
    ny0, ny1 = sorted((_clamp01(y0 / ph), _clamp01(y1 / ph)))
    return BoundingBox(x0=nx0, y0=ny0, x1=nx1, y1=ny1)


def _polygon_to_rect(polygon: Any) -> Tuple[float, float, float, float]:
    pts = np.asarray(polygon, dtype=np.float32).reshape(-1, 2)
    return (
        float(pts[:, 0].min()),
        float(pts[:, 1].min()),
        float(pts[:, 0].max()),
        float(pts[:, 1].max()),
    )


def _span(entity: Any) -> Tuple[int, int]:
    """Read (start, end) from a detector result (object or dict) regardless of naming."""
    if isinstance(entity, dict):
        start = entity.get("start", entity.get("start_char"))
        end = entity.get("end", entity.get("end_char"))
        if start is None or end is None:
            raise IngestionError("Detector result is missing start/end offsets")
        return int(start), int(end)
    start = next((getattr(entity, a) for a in ("start", "start_char") if hasattr(entity, a)), None)
    end = next((getattr(entity, a) for a in ("end", "end_char") if hasattr(entity, a)), None)
    if start is None or end is None:
        raise IngestionError("DetectedEntity is missing start/end offsets")
    return int(start), int(end)


def _encode_png_b64(bgr: np.ndarray) -> str:
    ok, buf = cv2.imencode(".png", bgr)
    if not ok:
        raise IngestionError("Failed to encode page preview as PNG")
    return base64.b64encode(buf.tobytes()).decode("ascii")


def _has_non_ascii(text: str) -> bool:
    return any(ord(c) > 127 for c in text)


def _make_entity(
    entity_type: str,
    page_no: int,
    line_no: int,
    text: str,
    conf: float,
    label: str,
) -> DetectedEntity:
    """Build a DetectedEntity for detections made outside HybridPIIDetector."""
    seed = f"p{page_no}_l{line_no}_0_{len(text)}_{entity_type}"
    return DetectedEntity(
        id=str(uuid.uuid5(uuid.NAMESPACE_OID, seed)),
        page=page_no,
        line_number=max(line_no, 1),
        entity_type=entity_type,
        category="CONTACT_PII",          # schemas.py only allows GOV_ID / FINANCIAL / CONTACT_PII / CUSTOM_BOX
        text_preview=text,
        start_char=0,
        end_char=len(text),
        confidence=conf,
        validator_passed=label,
        bbox=None,                       # geometry travels on Finding.bbox, like every other finding
        selected_for_redaction=True,
    )


def _haar_cascade_path() -> Optional[str]:
    candidates: List[str] = []
    data = getattr(cv2, "data", None)
    if data is not None and hasattr(data, "haarcascades"):
        candidates.append(os.path.join(data.haarcascades, _HAAR_FILE))
    candidates.append(os.path.join(os.path.dirname(cv2.__file__), "data", _HAAR_FILE))
    return next((p for p in candidates if os.path.isfile(p)), None)


# ----------------------------------------------------------------------------
# Ingestor
# ----------------------------------------------------------------------------
class DocumentIngestor:
    def __init__(self, detector: Optional[HybridPIIDetector] = None) -> None:
        self.detector = detector or HybridPIIDetector()
        self._ocr = None  # lazy: RapidOCR model load is expensive
        self._face_cascade = None
        self._face_cascade_failed = False

    def _detect(self, text: str, line_no: int = 1, page_no: int = 1) -> list:
        """Call detector.analyze_line, passing optional line/page args only if it accepts them."""
        fn = self.detector.analyze_line
        params = inspect.signature(fn).parameters
        extras = {}
        for name, value in (("line_number", line_no), ("page", page_no), ("page_number", page_no)):
            if name in params:
                extras[name] = value
        return list(fn(text, **extras) or [])

    # -- public API ----------------------------------------------------------
    def ingest(self, filename: str, data: bytes) -> IngestionResult:
        ext = os.path.splitext(filename)[1].lower()
        if ext == ".txt":
            return self.ingest_text(filename, data)
        if ext in IMAGE_EXTS:
            return self.ingest_image(filename, data)
        if ext == ".pdf":
            return self.ingest_pdf(filename, data)
        raise UnsupportedFormatError(f"Unsupported file type: '{ext or filename}'")

    # -- Path A: plain text --------------------------------------------------
    def ingest_text(self, filename: str, data: bytes) -> IngestionResult:
        try:
            text = data.decode("utf-8-sig", errors="replace")
        except Exception as exc:  # pragma: no cover
            raise IngestionError(f"Could not decode text file: {exc}") from exc

        page = PageResult(page_number=1, width=None, height=None, source="text")
        for idx, line in enumerate(text.splitlines(), start=1):
            page.raw_text_lines.append(
                TextLine(line_number=idx, text=line, start_char=0, end_char=len(line))
            )
            if not line.strip():
                continue
            for ent in self._detect(line, idx, 1):
                s, e = _span(ent)
                page.findings.append(
                    Finding(
                        entity=ent, page_number=1, line_number=idx,
                        start_char=s, end_char=e, text=line[s:e], bbox=None,
                    )
                )
        return IngestionResult(filename=filename, file_type="txt", pages=[page])

    # -- Path B: standalone images ------------------------------------------
    def ingest_image(self, filename: str, data: bytes) -> IngestionResult:
        arr = np.frombuffer(data, dtype=np.uint8)
        bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if bgr is None:
            raise IngestionError(f"Could not decode image: {filename}")
        page = self._process_bitmap(bgr, page_number=1, source="image")
        ext = os.path.splitext(filename)[1].lower().lstrip(".")
        return IngestionResult(filename=filename, file_type=ext, pages=[page])

    # -- Path C: PDFs --------------------------------------------------------
    def ingest_pdf(self, filename: str, data: bytes) -> IngestionResult:
        import pdfplumber
        import pypdfium2 as pdfium

        result = IngestionResult(filename=filename, file_type="pdf")
        try:
            pdf_doc = pdfium.PdfDocument(data)
            plumber = pdfplumber.open(io.BytesIO(data))
        except Exception as exc:
            raise IngestionError(f"Could not open PDF: {exc}") from exc

        try:
            for idx in range(len(pdf_doc)):
                page_number = idx + 1

                # 200-DPI RGB render: crisp preview + clean redaction canvas
                pdfium_page = pdf_doc[idx]
                try:
                    bitmap = pdfium_page.render(scale=PDF_RENDER_SCALE, rev_byteorder=True)
                    rgb = np.ascontiguousarray(bitmap.to_numpy())
                    if rgb.ndim == 3 and rgb.shape[2] == 4:
                        rgb = rgb[:, :, :3]
                finally:
                    pdfium_page.close()
                bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)

                plumber_page = plumber.pages[idx]
                n_chars = len(plumber_page.chars)

                if n_chars > DIGITAL_TEXT_MIN_CHARS:
                    page = self._process_digital_page(plumber_page, page_number)
                    # embedded photos in digital PDFs: boxes are normalized, so the render works
                    page.findings.extend(self._detect_faces(bgr, page_number))
                    page.preview_b64 = _encode_png_b64(bgr)
                    page.bitmap_rgb = rgb
                else:
                    page = self._process_bitmap(bgr, page_number, source="pdf_ocr")
                    page.bitmap_rgb = rgb
                result.pages.append(page)
                plumber_page.flush_cache()
        finally:
            plumber.close()
            pdf_doc.close()
        return result

    # -- Shared OCR pipeline (Path B and scanned-PDF fallback) ----------------
    def _run_ocr(self, bgr: np.ndarray) -> list:
        """Run OCR; returns [[polygon, text, conf], ...]. Supports both RapidOCR packages."""
        if self._ocr is None:
            errors: List[str] = []
            try:
                from rapidocr_onnxruntime import RapidOCR  # classic package (Python <= 3.12)
                self._ocr = ("legacy", RapidOCR())
            except Exception as exc:
                errors.append(f"rapidocr_onnxruntime: {exc!r}")
                try:
                    from rapidocr import RapidOCR  # newer package (works on Python 3.13)
                    self._ocr = ("new", RapidOCR())
                except Exception as exc2:
                    errors.append(f"rapidocr: {exc2!r}")
                    raise IngestionError(
                        "No OCR engine installed. Run: pip install rapidocr-onnxruntime "
                        "(or, on Python 3.13: pip install rapidocr onnxruntime). "
                        "Details: " + " | ".join(errors)
                    ) from exc2
        kind, engine = self._ocr
        if kind == "legacy":
            out, _elapsed = engine(bgr)
            return out or []
        res = engine(bgr)
        if res is None:
            return []
        boxes = getattr(res, "boxes", None)
        txts = getattr(res, "txts", None)
        scores = getattr(res, "scores", None)
        if boxes is None or txts is None or scores is None:
            return []
        return [[b, t, s] for b, t, s in zip(boxes, txts, scores)]

    def _process_bitmap(self, bgr: np.ndarray, page_number: int, source: str) -> PageResult:
        page_h, page_w = bgr.shape[:2]
        page = PageResult(
            page_number=page_number, width=float(page_w), height=float(page_h),
            source=source, preview_b64=_encode_png_b64(bgr),
            bitmap_rgb=cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB),
        )

        ocr_out = self._run_ocr(bgr)
        for line_no, item in enumerate(ocr_out, start=1):
            polygon, text, conf = item[0], item[1], item[2]
            text = text or ""
            rect = _polygon_to_rect(polygon)
            try:
                conf_f: Optional[float] = float(conf)
            except (TypeError, ValueError):
                conf_f = None

            page.raw_text_lines.append(
                TextLine(
                    line_number=line_no, text=text, start_char=0, end_char=len(text),
                    bbox=_normalize_box(*rect, page_w, page_h), ocr_conf=conf_f,
                )
            )
            if not text.strip():
                continue

            # Proportional character slicing is unreliable when the OCR text mixes scripts
            # (e.g. regional-script labels read as garbage), so cover the whole line then.
            full_line = _has_non_ascii(text)
            for ent in self._detect(text, line_no, page_number):
                s, e = _span(ent)
                if full_line:
                    bbox = _normalize_box(
                        rect[0] - BBOX_PAD_PX, rect[1] - BBOX_PAD_PX,
                        rect[2] + BBOX_PAD_PX, rect[3] + BBOX_PAD_PX, page_w, page_h,
                    )
                else:
                    bbox = slice_sub_bbox(rect, len(text), s, e, page_w, page_h)
                page.findings.append(
                    Finding(
                        entity=ent, page_number=page_number, line_number=line_no,
                        start_char=s, end_char=e, text=text[s:e], bbox=bbox,
                    )
                )

        self._apply_card_layout_rules(page)
        page.findings.extend(self._detect_faces(bgr, page_number))
        return page

    # -- ID-card layout rule ----------------------------------------------------
    def _apply_card_layout_rules(self, page: PageResult) -> None:
        """
        The detector works line by line with no NER, so a bare name line (no honorific, no
        'Name:' label) is invisible to it. On ID cards the holder's name is the capitalised
        line just above the DOB (or gender) line, with a regional-script copy above that.
        Only runs on pages that look like an ID card, so ordinary documents that happen to
        contain a 'Male' or 'DOB' line are not affected.
        """
        lines = page.raw_text_lines
        is_id_card = any(_ID_CARD_CUE.search(ln.text) for ln in lines) or any(
            getattr(f.entity, "entity_type", None) == "IN_AADHAAR" for f in page.findings
        )
        if not is_id_card:
            return
        anchor = next(
            (i for i, ln in enumerate(lines)
             if _DOB_CUE.search(ln.text) or _GENDER_LINE.search(ln.text)),
            None,
        )
        if anchor is None:
            return

        for j in range(anchor - 1, max(anchor - 4, -1), -1):
            txt = lines[j].text.strip()
            if not (_NAME_LINE.match(txt) and not _NOT_NAME.search(txt)):
                continue

            targets = [lines[j]]
            for k in (j - 1, j - 2):                       # regional-script copy of the name
                if k >= 0 and _has_non_ascii(lines[k].text):
                    targets.append(lines[k])
                    break

            for ln in targets:
                if ln.bbox is None or not ln.text.strip():
                    continue
                already = any(
                    f.line_number == ln.line_number
                    and getattr(f.entity, "entity_type", None) == "PERSON"
                    for f in page.findings
                )
                if already:
                    continue
                ent = _make_entity(
                    "PERSON", page.page_number, ln.line_number, ln.text, 0.80,
                    "ID Card Layout Rule",
                )
                page.findings.append(
                    Finding(
                        entity=ent, page_number=page.page_number, line_number=ln.line_number,
                        start_char=0, end_char=len(ln.text), text=ln.text, bbox=ln.bbox,
                    )
                )
            break

    # -- Face photos ------------------------------------------------------------
    def _get_face_cascade(self):
        if self._face_cascade is None and not self._face_cascade_failed:
            cascade = None
            try:
                path = _haar_cascade_path()
                if path:
                    cascade = cv2.CascadeClassifier(path)
            except Exception:
                cascade = None
            if cascade is None or cascade.empty():
                self._face_cascade_failed = True
                logger.warning(
                    "Haar face cascade not available; face redaction disabled "
                    '(try: pip install "opencv-python-headless<5")'
                )
            else:
                self._face_cascade = cascade
        return self._face_cascade

    def _detect_faces(self, bgr: np.ndarray, page_number: int) -> List[Finding]:
        cascade = self._get_face_cascade()
        if cascade is None:
            return []
        h, w = bgr.shape[:2]
        gray = cv2.equalizeHist(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY))
        min_side = max(24, min(w, h) // 25)
        faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5,
                                         minSize=(min_side, min_side))
        out: List[Finding] = []
        for i, (x, y, fw, fh) in enumerate(faces, start=1):
            x, y, fw, fh = int(x), int(y), int(fw), int(fh)
            # grow the box to cover the hair and shoulders of an ID photo
            box = _normalize_box(
                x - 0.4 * fw, y - 0.6 * fh, x + 1.4 * fw, y + 1.3 * fh, w, h
            )
            line_no = 1000 + i                      # synthetic: faces have no text line
            ent = _make_entity(
                FACE_ENTITY_TYPE, page_number, line_no, "[face photo]", 0.85,
                "Face Detector (Haar Cascade)",
            )
            out.append(
                Finding(
                    entity=ent, page_number=page_number, line_number=line_no,
                    start_char=0, end_char=0, text="", bbox=box,
                )
            )
        return out

    # -- Digital PDF page: pdfplumber char-exact mapping -----------------------
    def _process_digital_page(self, plumber_page: Any, page_number: int) -> PageResult:
        pw, ph = float(plumber_page.width), float(plumber_page.height)
        pad_pts = BBOX_PAD_PX / PDF_RENDER_SCALE   # 2 px at render DPI, in PDF points
        page = PageResult(
            page_number=page_number, width=pw, height=ph, source="pdf_digital"
        )

        for line_no, (text, char_map) in enumerate(self._build_lines(plumber_page.chars), start=1):
            line_chars = [c for c in char_map if c is not None]
            lx0 = min(c["x0"] for c in line_chars)
            lx1 = max(c["x1"] for c in line_chars)
            ly0 = min(c["top"] for c in line_chars)
            ly1 = max(c["bottom"] for c in line_chars)
            page.raw_text_lines.append(
                TextLine(
                    line_number=line_no, text=text, start_char=0, end_char=len(text),
                    bbox=_normalize_box(lx0, ly0, lx1, ly1, pw, ph),
                )
            )

            for ent in self._detect(text, line_no, page_number):
                s, e = _span(ent)
                s, e = max(s, 0), min(e, len(text))
                span_chars = [c for c in char_map[s:e] if c is not None]
                if not span_chars:
                    continue
                bbox = _normalize_box(
                    min(c["x0"] for c in span_chars) - pad_pts,
                    min(c["top"] for c in span_chars) - pad_pts,
                    max(c["x1"] for c in span_chars) + pad_pts,
                    max(c["bottom"] for c in span_chars) + pad_pts,
                    pw, ph,
                )
                page.findings.append(
                    Finding(
                        entity=ent, page_number=page_number, line_number=line_no,
                        start_char=s, end_char=e, text=text[s:e], bbox=bbox,
                    )
                )
        return page

    @staticmethod
    def _build_lines(chars: List[dict]) -> List[Tuple[str, List[Optional[dict]]]]:
        """
        Cluster pdfplumber chars into visual lines (by `top`), then rebuild each line's
        text together with a parallel list mapping every text index -> source char dict
        (None for synthetic spaces). This guarantees analyzer offsets map back exactly.
        """
        usable = [c for c in chars if c.get("text") and c.get("upright", True)]
        usable.sort(key=lambda c: (c["top"], c["x0"]))

        clusters: List[List[dict]] = []
        ref_tops: List[float] = []
        for ch in usable:
            tol = max(2.0, 0.5 * (ch["bottom"] - ch["top"]))
            if clusters and abs(ch["top"] - ref_tops[-1]) <= tol:
                clusters[-1].append(ch)
            else:
                clusters.append([ch])
                ref_tops.append(ch["top"])

        lines: List[Tuple[str, List[Optional[dict]]]] = []
        for cluster in clusters:
            cluster.sort(key=lambda c: c["x0"])
            out_text: List[str] = []
            out_map: List[Optional[dict]] = []
            prev: Optional[dict] = None
            for ch in cluster:
                if prev is not None and not ch["text"].isspace():
                    gap = ch["x0"] - prev["x1"]
                    ref_w = max(prev["x1"] - prev["x0"], ch["x1"] - ch["x0"], 1.0)
                    if gap > 0.25 * ref_w and out_text and not out_text[-1].isspace():
                        out_text.append(" ")
                        out_map.append(None)
                for t in ch["text"]:               # ligatures expand to several chars
                    out_text.append(t)
                    out_map.append(ch)
                prev = ch
            text = "".join(out_text)
            if text.strip() and any(m is not None for m in out_map):
                lines.append((text, out_map))
        return lines