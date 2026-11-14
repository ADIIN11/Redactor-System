import sys
from pathlib import Path
from backend.engine.ingestor import DocumentIngestor

path = Path(sys.argv[1])
result = DocumentIngestor().ingest(path.name, path.read_bytes())

def box(b):
    return "-" if b is None else f"({b.x0:.3f},{b.y0:.3f},{b.x1:.3f},{b.y1:.3f})"

for page in result.pages:
    print(f"=== page {page.page_number} [{page.source}] {page.width}x{page.height}")
    print("--- OCR lines:")
    for ln in page.raw_text_lines:
        print(f"L{ln.line_number:>2} {box(ln.bbox)} {ascii(ln.text)}")
    print("--- findings:")
    for f in page.findings:
        print(f"L{f.line_number:>2} {getattr(f.entity, 'entity_type', '?'):<14} bbox={box(f.bbox)} text={ascii(f.text)}")
