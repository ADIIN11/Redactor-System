# CB-02 // Classified Dossier Redaction Studio

Detects PII in `.txt`, `.pdf` and image files and produces a zero-leak redacted clone
(PDFs and images are rasterized and rebuilt, so no hidden text survives).

```
Redactor-System/
├── backend/            FastAPI + Presidio + RapidOCR + pdfplumber + pypdfium2
├── frontend/           Vite + React + Tailwind v4
├── scripts/            generate_demo_samples.py
└── demo_samples/       synthetic test files (generated)
```

**Prerequisites:** Python 3.11 or 3.12 (recommended: some ONNX/OCR wheels lag behind 3.13) and Node.js 18+.
Run every command below from the repo root (`Redactor-System/`) unless a `cd` is shown.

## 1. Python environment

**Windows (PowerShell)**
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r backend/requirements.txt reportlab
python -m spacy download en_core_web_lg
```

**macOS / Linux**
```bash
python3 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip
pip install -r backend/requirements.txt reportlab
python -m spacy download en_core_web_lg
```

`backend/requirements.txt` must include `fastapi`, `uvicorn[standard]`, `python-multipart`,
`presidio-analyzer`, `spacy`, `rapidocr-onnxruntime`, `onnxruntime`, `opencv-python-headless`,
`pdfplumber`, `pypdfium2`, `pillow`, `numpy`. `reportlab` is only needed for the demo generator.

## 2. Generate the demo files

```bash
python scripts/generate_demo_samples.py
```

Creates, inside `demo_samples/`:

| File | Path exercised |
|---|---|
| `01_classified_wire_transfer.txt` | Plain-text teleprinter view |
| `02_digital_kyc_onboarding.pdf` | Digital PDF, character-exact boxes |
| `03_scanned_vendor_invoice.png` | Noisy 1° tilted scan, RapidOCR + sub-line boxes |

Everything is synthetic. Aadhaar numbers are produced by a Verhoeff generator and card numbers by a
Luhn generator at runtime (fixed seed, so output is reproducible).

## 3. Start the backend (terminal 1)

```bash
uvicorn backend.main:app --reload --port 8000
```

> Run this from the repo root. The backend uses package imports (`backend.engine...`), so
> `uvicorn main:app` from inside `backend/` will fail with `ModuleNotFoundError`.

Check: http://localhost:8000/docs and http://localhost:8000/api/v1/health

## 4. Start the frontend (terminal 2)

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173, then drag in a file from `demo_samples/`.

If the frontend runs but the API calls fail, the backend URL can be overridden with
`VITE_API_URL=http://localhost:8000` in `frontend/.env`.

## Demo flow

1. Upload a sample and watch the **X-Ray Inspect** view color-code every finding.
2. Click boxes (or checkboxes) to include or exclude entities, or drag on the page to add a custom box.
3. Switch to **Live CIA Blackout Preview** to see the exact clone before exporting.
4. Pick a redaction mode, optionally enable the stamp, then press **Clone & Sanitize Document**.
5. The clone downloads automatically and the **Audit Certificate** shows both SHA-256 hashes.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `Cannot find package '@tailwindcss/vite'` | `cd frontend && npm install tailwindcss@4 "@tailwindcss/vite@4"` |
| `Cannot find module 'autoprefixer'` | Delete `frontend/postcss.config.js` and `frontend/tailwind.config.js` (Tailwind v4 doesn't use them) |
| `ModuleNotFoundError: backend` | Start uvicorn from the repo root with `backend.main:app` |
| `Form data requires "python-multipart"` | `pip install python-multipart` |
| spaCy model not found | `python -m spacy download en_core_web_lg` |
