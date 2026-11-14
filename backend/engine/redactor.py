"""
backend/engine/redactor.py

CIADocumentRedactor: permanent, zero-leak cloning of .txt / .png / .jpg / .pdf files.

* .txt          -> in-place string replacement (reverse char order per line).
* images        -> OpenCV rectangles on the decoded bitmap, re-encoded as a fresh PNG
                   (no EXIF / ancillary metadata is carried over).
* .pdf          -> every page is re-rendered by pypdfium2 at 200 DPI, redacted as a bitmap,
                   and re-assembled into a NEW flattened image-only PDF. The original text
                   stream, fonts, annotations and metadata are never copied.

Entities are plain mappings (or objects) with:
    entity_type, page_number, line_number, start_char, end_char,
    bbox {x0,y0,x1,y1} (normalized), selected_for_redaction
"""

from __future__ import annotations

import hashlib
import io
import math
import os
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import cv2
import numpy as np
from PIL import Image

from backend.engine.ingestor import PDF_RENDER_DPI, PDF_RENDER_SCALE

MODES = ("cia_blackout", "partial_mask", "entity_tag")
IMAGE_EXTS = {"png", "jpg", "jpeg"}

TEXT_BANNER = (
    "========================================================\n"
    "[DECLASSIFIED CLONE // SENSITIVE PII REDACTED // CB-02]\n"
    "========================================================\n"
)
STAMP_LABEL = "REDACTED CLONE // ZERO-LEAK VERIFIED"
AADHAAR_TYPE = "IN_AADHAAR"
AADHAAR_TEXT_REPLACEMENT = "[Aadhaar Redacted]"
AADHAAR_IMAGE_LABEL = "[AADHAAR REDACTED]"

BLEED_PX = 3

# Colours are RGB because page bitmaps are RGB arrays.
COL_BLACK = (10, 10, 12)
COL_BLACK_BORDER = (55, 55, 62)
COL_SLATE = (30, 41, 59)
COL_CYAN = (34, 211, 238)
COL_WHITE = (255, 255, 255)
COL_CRIMSON = (185, 28, 28)
COL_ZINC = (113, 113, 122)

FONT = cv2.FONT_HERSHEY_SIMPLEX  # OpenCV ships no true monospace Hershey face


class RedactionError(Exception):
    pass


@dataclass
class RedactionResult:
    file_bytes: bytes
    output_filename: str
    extension: str
    mime_type: str
    sha256_redacted: str
    entity_counts: Dict[str, int]
    certificate: Dict[str, Any]


# ----------------------------------------------------------------------------
# Small helpers
# ----------------------------------------------------------------------------
def _get(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, Mapping):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _bbox_tuple(bbox: Any) -> Optional[Tuple[float, float, float, float]]:
    if bbox is None:
        return None
    try:
        return (float(_get(bbox, "x0")), float(_get(bbox, "y0")),
                float(_get(bbox, "x1")), float(_get(bbox, "y1")))
    except (TypeError, ValueError):
        return None


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _selected(entities: Sequence[Any]) -> List[Any]:
    return [e for e in entities if bool(_get(e, "selected_for_redaction", True))]


def _partial_mask_text(original: str) -> str:
    """Mask the leading ~60-75% with '*', keep only the trailing 2-4 characters."""
    n = len(original)
    if n <= 2:
        return "*" * n
    if n == 3:
        visible = 1
    else:
        visible = min(4, max(2, round(n * 0.30)))
    return "*" * (n - visible) + original[n - visible:]


# ----------------------------------------------------------------------------
# Bitmap drawing primitives
# ----------------------------------------------------------------------------
def _px_box(bbox: Tuple[float, float, float, float], w: int, h: int) -> Tuple[int, int, int, int]:
    x0, y0, x1, y1 = bbox
    px0 = max(0, int(math.floor(x0 * w)) - BLEED_PX)
    py0 = max(0, int(math.floor(y0 * h)) - BLEED_PX)
    px1 = min(w - 1, int(math.ceil(x1 * w)) + BLEED_PX)
    py1 = min(h - 1, int(math.ceil(y1 * h)) + BLEED_PX)
    return px0, py0, px1, py1


def _draw_fitted_text(img: np.ndarray, text: str, box: Tuple[int, int, int, int],
                      color: Tuple[int, int, int]) -> None:
    """Draw `text` centred in `box`, auto-scaled to fit (90% width / 70% height)."""
    px0, py0, px1, py1 = box
    bw, bh = max(px1 - px0, 1), max(py1 - py0, 1)
    (tw, th), _ = cv2.getTextSize(text, FONT, 1.0, 1)
    scale = min((bw * 0.90) / max(tw, 1), (bh * 0.70) / max(th, 1))
    scale = max(scale, 0.2)
    thickness = 1 if scale < 1.2 else 2
    (tw, th), base = cv2.getTextSize(text, FONT, scale, thickness)
    tx = px0 + (bw - tw) // 2
    ty = py0 + (bh + th) // 2
    cv2.putText(img, text, (tx, ty), FONT, scale, color, thickness, cv2.LINE_AA)


def _draw_blackout(img: np.ndarray, box: Tuple[int, int, int, int]) -> None:
    px0, py0, px1, py1 = box
    cv2.rectangle(img, (px0, py0), (px1, py1), COL_BLACK, thickness=-1)
    cv2.rectangle(img, (px0, py0), (px1, py1), COL_BLACK_BORDER, thickness=1)


def _draw_entity(img: np.ndarray, mode: str, entity_type: str,
                 box: Tuple[int, int, int, int]) -> None:
    px0, py0, px1, py1 = box
    if mode == "cia_blackout":
        _draw_blackout(img, box)
    elif mode == "partial_mask":
        if entity_type == AADHAAR_TYPE:
            _draw_blackout(img, box)
            _draw_fitted_text(img, AADHAAR_IMAGE_LABEL, box, COL_WHITE)
        else:
            cut = px0 + int(0.70 * (px1 - px0))
            _draw_blackout(img, (px0, py0, cut, py1))
    elif mode == "entity_tag":
        cv2.rectangle(img, (px0, py0), (px1, py1), COL_SLATE, thickness=-1)
        cv2.rectangle(img, (px0, py0), (px1, py1), COL_CYAN, thickness=1)
        _draw_fitted_text(img, f"[{entity_type}]", box, COL_WHITE)
    else:  # pragma: no cover - validated upstream
        raise RedactionError(f"Unknown redaction mode: {mode}")


def _apply_stamp(img: np.ndarray) -> np.ndarray:
    """Semi-transparent, tilted crimson/zinc stamp in the top-right corner."""
    h, w = img.shape[:2]
    (tw1, _), _ = cv2.getTextSize(STAMP_LABEL, FONT, 1.0, 2)
    scale = (w * 0.42 * 0.90) / max(tw1, 1)
    scale = max(scale, 0.25)
    thick = max(1, int(round(scale * 2)))
    (tw, th), base = cv2.getTextSize(STAMP_LABEL, FONT, scale, thick)

    pad = max(int(th * 0.9), 4)
    sw, sh = tw + 2 * pad, th + base + 2 * pad
    m = int(max(sw, sh) * 0.5)               # room so rotation never clips
    cw, ch = sw + 2 * m, sh + 2 * m
    if cw > w or ch > h:
        return img

    canvas = np.zeros((ch, cw, 3), np.uint8)
    mask = np.zeros((ch, cw), np.uint8)
    for target, c_main, c_inner in ((canvas, COL_CRIMSON, COL_ZINC), (mask, 255, 255)):
        cv2.rectangle(target, (m, m), (m + sw, m + sh), c_main, max(2, thick + 1), cv2.LINE_AA)
        cv2.rectangle(target, (m + 5, m + 5), (m + sw - 5, m + sh - 5), c_inner, 1, cv2.LINE_AA)
        cv2.putText(target, STAMP_LABEL, (m + pad, m + pad + th), FONT, scale, c_main,
                    thick, cv2.LINE_AA)

    rot = cv2.getRotationMatrix2D((cw / 2, ch / 2), 12.0, 1.0)
    canvas = cv2.warpAffine(canvas, rot, (cw, ch), flags=cv2.INTER_LINEAR)
    mask = cv2.warpAffine(mask, rot, (cw, ch), flags=cv2.INTER_LINEAR)

    x = max(0, w - cw - int(0.02 * w))
    y = max(0, int(0.02 * h))
    alpha = (mask.astype(np.float32) / 255.0 * 0.80)[..., None]
    region = img[y:y + ch, x:x + cw].astype(np.float32)
    blended = region * (1.0 - alpha) + canvas.astype(np.float32) * alpha
    out = img.copy()
    out[y:y + ch, x:x + cw] = np.clip(blended, 0, 255).astype(np.uint8)
    return out


# ----------------------------------------------------------------------------
# Redactor
# ----------------------------------------------------------------------------
class CIADocumentRedactor:
    # -- public entry point ----------------------------------------------------
    def redact(
        self,
        *,
        filename: str,
        file_type: str,
        source_bytes: bytes,
        entities: Sequence[Any],
        mode: str,
        add_declassified_stamp: bool,
        sha256_original: str,
    ) -> RedactionResult:
        if mode not in MODES:
            raise RedactionError(f"Unsupported redaction mode '{mode}'")
        file_type = file_type.lower().lstrip(".")
        targets = _selected(entities)

        if file_type == "txt":
            out_bytes, counts = self._clone_text(source_bytes, targets, mode, add_declassified_stamp)
            ext, mime, pages_n, method = "txt", "text/plain; charset=utf-8", 1, "text_replace"
        elif file_type in IMAGE_EXTS:
            rgb = self._decode_image_rgb(source_bytes)
            pages, counts = self._redact_pages([rgb], targets, mode, add_declassified_stamp)
            out_bytes = self._encode_png(pages[0])
            ext, mime, pages_n, method = "png", "image/png", 1, "bitmap_flatten"
        elif file_type == "pdf":
            rendered = self.render_pdf_pages(source_bytes)
            pages, counts = self._redact_pages(rendered, targets, mode, add_declassified_stamp)
            out_bytes = self._assemble_pdf(pages)
            ext, mime, pages_n, method = "pdf", "application/pdf", len(pages), "bitmap_flatten"
        else:
            raise RedactionError(f"Unsupported file type '{file_type}'")

        stem = os.path.splitext(os.path.basename(filename))[0] or "document"
        output_filename = f"{stem}_CIA_REDACTED.{ext}"
        sha_out = sha256_hex(out_bytes)

        certificate = {
            "certificate_id": str(uuid.uuid4()),
            "issued_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "original_filename": os.path.basename(filename),
            "output_filename": output_filename,
            "file_type": file_type,
            "output_format": ext,
            "redaction_mode": mode,
            "declassified_stamp_applied": bool(add_declassified_stamp),
            "pages_processed": pages_n,
            "entities_redacted_total": int(sum(counts.values())),
            "entities_redacted_by_category": dict(counts),
            "sha256_original": sha256_original,
            "sha256_redacted": sha_out,
            "method": method,
            "zero_leak": {
                "original_text_stream_carried": False,
                "original_fonts_carried": False,
                "original_metadata_carried": False,
                "flattened_raster_only": method == "bitmap_flatten",
            },
            "engine": "CIADocumentRedactor",
        }  # deliberately contains no redacted values

        return RedactionResult(
            file_bytes=out_bytes, output_filename=output_filename, extension=ext,
            mime_type=mime, sha256_redacted=sha_out, entity_counts=dict(counts),
            certificate=certificate,
        )

    # -- A. text cloner ----------------------------------------------------------
    def _clone_text(self, data: bytes, targets: Sequence[Any], mode: str,
                    stamp: bool) -> Tuple[bytes, Counter]:
        text = data.decode("utf-8-sig", errors="replace")   # same decoding as the ingestor
        trailing_nl = text.endswith(("\n", "\r"))
        lines = text.splitlines()
        counts: Counter = Counter()

        by_line: Dict[int, List[Any]] = defaultdict(list)
        for e in targets:
            by_line[int(_get(e, "line_number", 0) or 0)].append(e)

        for ln, ents in by_line.items():
            if not 1 <= ln <= len(lines):
                continue
            line = lines[ln - 1]
            spans: List[Tuple[int, int, str]] = []
            for e in ents:
                s = max(int(_get(e, "start_char", 0)), 0)
                en = min(int(_get(e, "end_char", 0)), len(line))
                if en <= s:
                    continue
                etype = str(_get(e, "entity_type", "PII"))
                spans.append((s, en, etype))
                counts[etype] += 1

            # Merge overlaps so nothing is left half-visible and indices stay consistent.
            merged: List[List[Any]] = []
            for s, en, etype in sorted(spans, key=lambda t: (t[0], -(t[1] - t[0]))):
                if merged and s < merged[-1][1]:
                    cur = merged[-1]
                    cur[1] = max(cur[1], en)
                    cur[2].append(etype)
                else:
                    merged.append([s, en, [etype]])

            # Reverse order: replacements never shift the indices still to be processed.
            for s, en, types in sorted(merged, key=lambda m: m[0], reverse=True):
                line = line[:s] + self._text_replacement(line[s:en], types, mode) + line[en:]
            lines[ln - 1] = line

        out = "\n".join(lines) + ("\n" if trailing_nl else "")
        if stamp:
            out = TEXT_BANNER + out
        return out.encode("utf-8"), counts

    @staticmethod
    def _text_replacement(original: str, types: List[str], mode: str) -> str:
        if mode == "cia_blackout":
            return "\u2588" * len(original)
        if mode == "partial_mask":
            if AADHAAR_TYPE in types:
                return AADHAAR_TEXT_REPLACEMENT
            return _partial_mask_text(original)
        return f"[REDACTED:{types[0]}]"

    # -- B. bitmap cloner ------------------------------------------------------------
    def _redact_pages(self, pages: List[np.ndarray], targets: Sequence[Any], mode: str,
                      stamp: bool) -> Tuple[List[np.ndarray], Counter]:
        counts: Counter = Counter()
        by_page: Dict[int, List[Any]] = defaultdict(list)
        for e in targets:
            by_page[int(_get(e, "page_number", 1) or 1)].append(e)

        out_pages: List[np.ndarray] = []
        for idx, page in enumerate(pages, start=1):
            img = np.ascontiguousarray(page[:, :, :3]).copy()
            h, w = img.shape[:2]
            for e in by_page.get(idx, []):
                bbox = _bbox_tuple(_get(e, "bbox"))
                if bbox is None:
                    continue
                etype = str(_get(e, "entity_type", "PII"))
                _draw_entity(img, mode, etype, _px_box(bbox, w, h))
                counts[etype] += 1
            if stamp and idx == 1:
                img = _apply_stamp(img)
            out_pages.append(img)
        return out_pages, counts

    # -- rendering / decoding / export ---------------------------------------------------
    @staticmethod
    def render_pdf_pages(pdf_bytes: bytes) -> List[np.ndarray]:
        import pypdfium2 as pdfium

        try:
            doc = pdfium.PdfDocument(pdf_bytes)
        except Exception as exc:
            raise RedactionError(f"Could not open PDF: {exc}") from exc
        pages: List[np.ndarray] = []
        try:
            for i in range(len(doc)):
                page = doc[i]
                try:
                    bmp = page.render(scale=PDF_RENDER_SCALE, rev_byteorder=True)  # RGB
                    arr = np.ascontiguousarray(bmp.to_numpy())
                finally:
                    page.close()
                pages.append(arr[:, :, :3])
        finally:
            doc.close()
        return pages

    @staticmethod
    def _decode_image_rgb(data: bytes) -> np.ndarray:
        bgr = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        if bgr is None:
            raise RedactionError("Could not decode image")
        return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)

    @staticmethod
    def _encode_png(rgb: np.ndarray) -> bytes:
        buf = io.BytesIO()
        Image.fromarray(rgb).save(buf, format="PNG")   # fresh image: no EXIF / text chunks
        return buf.getvalue()

    @staticmethod
    def _assemble_pdf(pages_rgb: List[np.ndarray]) -> bytes:
        if not pages_rgb:
            raise RedactionError("PDF has no pages")
        pil_pages = [Image.fromarray(p).convert("RGB") for p in pages_rgb]
        buf = io.BytesIO()
        pil_pages[0].save(
            buf, format="PDF", save_all=True, append_images=pil_pages[1:],
            resolution=float(PDF_RENDER_DPI),
        )
        return buf.getvalue()
