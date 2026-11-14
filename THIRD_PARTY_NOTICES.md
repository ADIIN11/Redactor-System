# Third-Party Open-Source Software Notices & License Disclosures

**Project:** CB-02 — Classified Dossier & Sensitive Information Redaction Studio  
**License Compliance Policy:** 100% Permissive Open-Source Stack (MIT, Apache-2.0, BSD-3-Clause, MIT-CMU). Zero AGPL/GPL copyleft dependencies are used in this system.

---

## 1. Backend Intelligence, OCR & Document Processing Components

| Component | Package Name | License | Copyright / Maintainer | Usage in CB-02 |
|---|---|---|---|---|
| **Microsoft Presidio Analyzer** | `presidio-analyzer` | MIT License | Microsoft Corporation | Context-aware PII entity recognition and custom pattern orchestration |
| **Microsoft Presidio Anonymizer** | `presidio-anonymizer` | MIT License | Microsoft Corporation | Redaction and masking operators for text streams |
| **spaCy NLP** | `spacy` (`en_core_web_lg`) | MIT License | Explosion AI | Named Entity Recognition (NER) for Person, Organization, and Location spans |
| **RapidOCR (PP-OCRv4 ONNX)** | `rapidocr-onnxruntime` | Apache License 2.0 | RapidAI / PaddleOCR Contributors | Offline optical character recognition and 4-point polygon bounding box extraction |
| **pdfplumber** | `pdfplumber` | MIT License | Jeremy Singer-Vine | Native digital PDF character and word coordinate extraction |
| **pypdfium2** | `pypdfium2` | Apache License 2.0 / BSD-3-Clause | pypdfium2 Team / Google PDFium | High-speed 200-DPI PDF page rasterization for preview and zero-leak flattening |
| **OpenCV (Headless)** | `opencv-python-headless` | Apache License 2.0 | OpenCV Team | Pixel-level CIA blackout bar rendering, semantic tag overlays, and image encoding |
| **Pillow (PIL Fork)** | `Pillow` | MIT-CMU License | Jeffrey A. Clark & Contributors | Multi-page flattened PDF assembly and EXIF metadata stripping |
| **ReportLab Toolkit** | `reportlab` | BSD-3-Clause License | ReportLab Inc. | Synthetic test dossier generation and PDF compliance certificates |
| **FastAPI** | `fastapi` | MIT License | Sebastián Ramírez | Asynchronous REST API server for ingestion and redaction pipelines |
| **Uvicorn** | `uvicorn` | BSD-3-Clause License | Encode OSS Ltd. | ASGI web server implementation for Python |
| **Pydantic** | `pydantic` | MIT License | Samuel Colvin & Contributors | Data validation and API schema serialization |

---

## 2. Frontend Workstation UI Components

| Component | Package Name | License | Copyright / Maintainer | Usage in CB-02 |
|---|---|---|---|---|
| **React & React DOM** | `react`, `react-dom` | MIT License | Meta Platforms, Inc. | Interactive UI rendering and canvas state management |
| **Vite** | `vite` | MIT License | Evan You & Vite Contributors | Frontend build tooling and development server |
| **Tailwind CSS** | `tailwindcss` | MIT License | Tailwind Labs, Inc. | Tactical dark-mode workstation styling |
| **Lucide Icons** | `lucide-react` | ISC / MIT License | Lucide Contributors | Vector iconography for security telemetry and redaction controls |