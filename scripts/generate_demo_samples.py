#!/usr/bin/env python3
"""
scripts/generate_demo_samples.py

Generates three SYNTHETIC hackathon test documents into <repo>/demo_samples/:

  01_classified_wire_transfer.txt   plain-text banking dispatch
  02_digital_kyc_onboarding.pdf     digital-born PDF (reportlab)
  03_scanned_vendor_invoice.png     noisy, 1-degree-tilted "scan" (Pillow + OpenCV)

All identifiers are randomly generated at runtime from a fixed seed (reproducible).
Aadhaar numbers come from a Verhoeff generator and card numbers from a Luhn generator,
so no ID literals are hardcoded. None of this data belongs to a real person.

Usage (from the repo root):  python scripts/generate_demo_samples.py
"""

from __future__ import annotations

import random
import string
from pathlib import Path
from typing import Dict, List

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "demo_samples"
SEED = 2026

# ----------------------------------------------------------------------------
# Checksum generators
# ----------------------------------------------------------------------------
_D = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 2, 3, 4, 0, 6, 7, 8, 9, 5],
    [2, 3, 4, 0, 1, 7, 8, 9, 5, 6], [3, 4, 0, 1, 2, 8, 9, 5, 6, 7],
    [4, 0, 1, 2, 3, 9, 5, 6, 7, 8], [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
    [6, 5, 9, 8, 7, 1, 0, 4, 3, 2], [7, 6, 5, 9, 8, 2, 1, 0, 4, 3],
    [8, 7, 6, 5, 9, 3, 2, 1, 0, 4], [9, 8, 7, 6, 5, 4, 3, 2, 1, 0],
]
_P = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 5, 7, 6, 2, 8, 3, 0, 9, 4],
    [5, 8, 0, 3, 7, 9, 6, 1, 4, 2], [8, 9, 1, 6, 0, 4, 3, 5, 2, 7],
    [9, 4, 5, 3, 1, 2, 6, 8, 7, 0], [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
    [2, 7, 9, 3, 8, 0, 6, 4, 1, 5], [7, 0, 4, 6, 9, 1, 3, 2, 5, 8],
]
_INV = [0, 4, 3, 2, 1, 5, 6, 7, 8, 9]


def verhoeff_check_digit(payload: str) -> str:
    c = 0
    for i, ch in enumerate(reversed(payload)):
        c = _D[c][_P[(i + 1) % 8][int(ch)]]
    return str(_INV[c])


def verhoeff_valid(number: str) -> bool:
    c = 0
    for i, ch in enumerate(reversed(number)):
        c = _D[c][_P[i % 8][int(ch)]]
    return c == 0


def luhn_check_digit(payload: str) -> str:
    total = 0
    for i, ch in enumerate(reversed(payload)):
        n = int(ch)
        if i % 2 == 0:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return str((10 - total % 10) % 10)


def luhn_valid(number: str) -> bool:
    return luhn_check_digit(number[:-1]) == number[-1]


# ----------------------------------------------------------------------------
# Synthetic identity factory
# ----------------------------------------------------------------------------
FIRST = ["Aarav", "Meera", "Rohan", "Ananya", "Vikram", "Kavya", "Arjun", "Ishita", "Rahul", "Neha"]
LAST = ["Sharma", "Iyer", "Banerjee", "Reddy", "Kulkarni", "Nair", "Chatterjee", "Menon", "Joshi", "Desai"]
BANKS = ["SBIN", "HDFC", "ICIC", "UTIB", "PUNB"]
BANK_NAMES = {"SBIN": "State Bank", "HDFC": "HDFC Bank", "ICIC": "ICICI Bank", "UTIB": "Axis Bank", "PUNB": "Punjab National Bank"}


def _digits(rng: random.Random, n: int) -> str:
    return "".join(rng.choice(string.digits) for _ in range(n))


def make_identity(rng: random.Random) -> Dict[str, str]:
    first, last = rng.choice(FIRST), rng.choice(LAST)
    name = f"{first} {last}"

    # PAN: AAAPL9999A (4th char = holder type 'P', 5th = surname initial)
    pan = "".join(rng.choices(string.ascii_uppercase, k=3)) + "P" + last[0].upper() \
        + _digits(rng, 4) + rng.choice(string.ascii_uppercase)

    payload = str(rng.randint(2, 9)) + _digits(rng, 10)
    raw = payload + verhoeff_check_digit(payload)
    assert verhoeff_valid(raw)
    aadhaar = f"{raw[:4]} {raw[4:8]} {raw[8:]}"

    if rng.random() < 0.5:
        body = "4" + _digits(rng, 14)                       # Visa-style
    else:
        body = "5" + str(rng.randint(1, 5)) + _digits(rng, 13)  # Mastercard-style
    card_raw = body + luhn_check_digit(body)
    assert luhn_valid(card_raw)
    card = " ".join(card_raw[i:i + 4] for i in range(0, 16, 4))

    bank = rng.choice(BANKS)
    ifsc = f"{bank}0{_digits(rng, 6)}"
    account = str(rng.randint(1, 9)) + _digits(rng, rng.randint(11, 15))
    mob = str(rng.randint(6, 9)) + _digits(rng, 9)
    phone = f"+91 {mob[:5]} {mob[5:]}"
    email = f"{first}.{last}".lower() + rng.choice(["@example.com", "@example.in", "@demo-mail.org"])

    return {
        "name": name, "pan": pan, "aadhaar": aadhaar, "card": card, "ifsc": ifsc,
        "bank": BANK_NAMES[bank], "account": account, "phone": phone, "email": email,
        "expiry": f"{rng.randint(1, 12):02d}/{rng.randint(28, 31)}",
    }


# ----------------------------------------------------------------------------
# 1. Plain-text wire dispatch
# ----------------------------------------------------------------------------
def generate_txt(path: Path, orig: Dict[str, str], benef: Dict[str, str]) -> None:
    lines = [
        "CLASSIFIED // INTERBANK WIRE DISPATCH // PRIORITY: IMMEDIATE",
        "================================================================",
        "FROM    : Treasury Operations, Meridian Trust Bank Ltd.",
        "TO      : Settlements Desk, Northbridge Clearing House",
        "DATE    : 14-NOV-2026 09:42 IST",
        "REF NO  : MTB/WIRE/2026/00417",
        "================================================================",
        "",
        "1. ORIGINATOR DETAILS",
        f"   Originator Name       : {orig['name']}",
        f"   Originator PAN        : {orig['pan']}",
        f"   Originator Aadhaar    : {orig['aadhaar']}",
        f"   Registered Mobile     : {orig['phone']}",
        f"   Registered Email      : {orig['email']}",
        f"   Corporate Card Used   : {orig['card']}",
        "",
        "2. BENEFICIARY DETAILS",
        f"   Beneficiary Name      : {benef['name']}",
        f"   Beneficiary A/c No: {benef['account']}",
        f"   Beneficiary Bank      : {benef['bank']}",
        f"   Beneficiary IFSC      : {benef['ifsc']}",
        f"   Beneficiary PAN       : {benef['pan']}",
        f"   Beneficiary Contact   : {benef['phone']}",
        f"   Notify Email          : {benef['email']}",
        "",
        "3. TRANSFER INSTRUCTION",
        "   Amount                : INR 48,75,000.00",
        "   Purpose               : Settlement of vendor milestone payment",
        "   Mode                  : RTGS",
        "",
        "Please confirm receipt and release funds before the 15:30 cut-off.",
        "Any discrepancy must be escalated to the compliance desk immediately.",
        "",
        "-- END OF DISPATCH --",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ----------------------------------------------------------------------------
# 2. Digital-born KYC PDF
# ----------------------------------------------------------------------------
def generate_pdf(path: Path, p: Dict[str, str]) -> None:
    styles = getSampleStyleSheet()
    title = ParagraphStyle("t", parent=styles["Title"], fontSize=17, textColor=colors.HexColor("#0f172a"))
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontSize=12, textColor=colors.HexColor("#1e3a8a"))
    body = styles["BodyText"]

    def table(rows: List[List[str]]) -> Table:
        t = Table(rows, colWidths=[55 * mm, 110 * mm])
        t.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#94a3b8")),
            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#e2e8f0")),
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ]))
        return t

    doc = SimpleDocTemplate(
        str(path), pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm,
        topMargin=18 * mm, bottomMargin=18 * mm, title="Customer Onboarding Dossier",
    )
    story = [
        Paragraph("CUSTOMER ONBOARDING &amp; FINANCIAL VERIFICATION DOSSIER", title),
        Paragraph("Meridian Trust Bank Ltd. | Retail KYC Division | File No: KYC/2026/88213", body),
        Spacer(1, 8 * mm),
        Paragraph("SECTION A - APPLICANT PARTICULARS", h2),
        table([
            ["Full Name", p["name"]],
            ["PAN Number", p["pan"]],
            ["Aadhaar Number", p["aadhaar"]],
            ["Mobile Number", p["phone"]],
            ["Email Address", p["email"]],
        ]),
        Spacer(1, 6 * mm),
        Paragraph("SECTION B - BANKING DETAILS", h2),
        table([
            ["Bank Name", p["bank"]],
            ["Bank A/c No", p["account"]],
            ["IFSC Code", p["ifsc"]],
            ["Account Type", "Savings"],
        ]),
        Spacer(1, 6 * mm),
        Paragraph("SECTION C - CARD INSTRUMENT ON FILE", h2),
        table([
            ["Card Number", p["card"]],
            ["Card Holder", p["name"].upper()],
            ["Valid Thru", p["expiry"]],
        ]),
        Spacer(1, 8 * mm),
        Paragraph(
            "I hereby declare that the information furnished above is true and correct to the "
            "best of my knowledge. I authorise the bank to verify these details with the "
            "relevant issuing authorities for the purpose of account onboarding.",
            body,
        ),
        Spacer(1, 14 * mm),
        Paragraph("Applicant Signature: ______________________ &nbsp;&nbsp;&nbsp; Date: 14-Nov-2026", body),
    ]
    doc.build(story)


# ----------------------------------------------------------------------------
# 3. Scanned invoice PNG
# ----------------------------------------------------------------------------
_FONT_CANDIDATES = {
    False: ["arial.ttf", "Arial.ttf", "DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/Library/Fonts/Arial.ttf", "/System/Library/Fonts/Supplemental/Arial.ttf"],
    True: ["arialbd.ttf", "Arial Bold.ttf", "DejaVuSans-Bold.ttf",
           "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
           "/System/Library/Fonts/Supplemental/Arial Bold.ttf"],
}


def _font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    for name in _FONT_CANDIDATES[bold]:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def _scanify(pil_img: Image.Image, seed: int) -> np.ndarray:
    """Paper tint, uneven lighting, blur, grain, speckles and a 1-degree tilt."""
    rng = np.random.default_rng(seed)
    img = cv2.cvtColor(np.array(pil_img.convert("RGB")), cv2.COLOR_RGB2BGR).astype(np.float32) / 255.0
    h, w = img.shape[:2]

    paper = np.array([0.89, 0.93, 0.96], np.float32)            # warm off-white (BGR)
    img *= paper
    xx = np.linspace(-1, 1, w, dtype=np.float32)[None, :]
    yy = np.linspace(-1, 1, h, dtype=np.float32)[:, None]
    shade = 1.0 - 0.07 * (xx ** 2 + yy ** 2) / 2 - 0.03 * (xx + 1) / 2
    img *= shade[..., None]

    img = cv2.GaussianBlur(img, (0, 0), 0.7)
    img += rng.normal(0, 0.028, (h, w, 1)).astype(np.float32)   # paper grain
    out = np.clip(img * 255.0, 0, 255).astype(np.uint8)

    for _ in range(400):                                          # dust specks
        x, y = int(rng.integers(0, w)), int(rng.integers(0, h))
        g = int(rng.integers(90, 170))
        cv2.circle(out, (x, y), int(rng.integers(0, 2)), (g, g, g), -1)

    rot = cv2.getRotationMatrix2D((w / 2, h / 2), 1.0, 1.0)       # 1-degree scan tilt
    bg = tuple(int(c) for c in (paper * 0.92 * 255))
    return cv2.warpAffine(out, rot, (w, h), flags=cv2.INTER_CUBIC,
                          borderMode=cv2.BORDER_CONSTANT, borderValue=bg)


def generate_scan(path: Path, v: Dict[str, str]) -> None:
    W, H = 1240, 1754
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    ink = (20, 20, 24)
    f_title, f_h, f_b, f_s = _font(64, True), _font(36, True), _font(32), _font(28)

    d.text((90, 80), "TAX INVOICE", font=f_title, fill=ink)
    d.text((90, 180), "Sundaram Precision Components Pvt. Ltd.", font=f_h, fill=ink)
    d.text((90, 230), "Plot 42, Phase II, Peenya Industrial Area, Bengaluru 560058", font=f_s, fill=ink)
    d.text((820, 100), "Invoice No: INV-2026-004187", font=f_b, fill=ink)
    d.text((820, 150), "Date: 12-Nov-2026", font=f_b, fill=ink)
    d.line((90, 290, W - 90, 290), fill=ink, width=3)

    d.text((90, 320), "BILL TO", font=f_h, fill=ink)
    d.text((90, 370), "Meridian Trust Bank Ltd., Corporate Procurement", font=f_b, fill=ink)
    d.text((90, 415), "Level 9, Harbour Tower, Mumbai 400001", font=f_s, fill=ink)

    # Line items
    y = 500
    cols = (90, 640, 800, 1000)
    for x, label in zip(cols, ("Description", "Qty", "Rate (INR)", "Amount (INR)")):
        d.text((x, y), label, font=f_h, fill=ink)
    d.line((90, y + 52, W - 90, y + 52), fill=ink, width=2)
    items = [("CNC Machined Bracket A12", 120, 485.00), ("Hardened Steel Shaft S7", 80, 1260.50),
             ("Precision Bearing Housing", 45, 2310.00)]
    y += 75
    subtotal = 0.0
    for desc, qty, rate in items:
        amt = qty * rate
        subtotal += amt
        for x, text in zip(cols, (desc, str(qty), f"{rate:,.2f}", f"{amt:,.2f}")):
            d.text((x, y), text, font=f_b, fill=ink)
        y += 52
    gst = subtotal * 0.18
    d.line((90, y + 5, W - 90, y + 5), fill=ink, width=2)
    d.text((640, y + 25), f"Subtotal: {subtotal:,.2f}", font=f_b, fill=ink)
    d.text((640, y + 75), f"GST @ 18%: {gst:,.2f}", font=f_b, fill=ink)
    d.text((640, y + 125), f"TOTAL: INR {subtotal + gst:,.2f}", font=f_h, fill=ink)

    y += 230
    d.line((90, y, W - 90, y), fill=ink, width=3)
    d.text((90, y + 25), "PAYMENT & VENDOR DETAILS", font=f_h, fill=ink)
    pii_lines = [
        f"Vendor PAN: {v['pan']}",
        f"Proprietor Aadhaar: {v['aadhaar']}",
        f"Beneficiary A/c No: {v['account']}",
        f"Bank IFSC: {v['ifsc']}",
        f"Accounts Contact: {v['phone']}",
        f"Remittance Email: {v['email']}",
    ]
    y += 90
    for text in pii_lines:
        d.text((90, y), text, font=f_b, fill=ink)
        y += 58

    d.text((90, H - 200), "Payment due within 30 days. Subject to Bengaluru jurisdiction.", font=f_s, fill=ink)
    d.text((820, H - 140), "Authorised Signatory", font=f_s, fill=ink)

    scanned = _scanify(img, SEED)
    ok, buf = cv2.imencode(".png", scanned)
    if not ok:
        raise RuntimeError("PNG encoding failed")
    path.write_bytes(buf.tobytes())


# ----------------------------------------------------------------------------
def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rng = random.Random(SEED)
    originator, beneficiary, applicant, vendor = (make_identity(rng) for _ in range(4))

    outputs = [
        (OUT_DIR / "01_classified_wire_transfer.txt", lambda p: generate_txt(p, originator, beneficiary)),
        (OUT_DIR / "02_digital_kyc_onboarding.pdf", lambda p: generate_pdf(p, applicant)),
        (OUT_DIR / "03_scanned_vendor_invoice.png", lambda p: generate_scan(p, vendor)),
    ]
    for path, build in outputs:
        build(path)
        print(f"  created {path.relative_to(ROOT)}  ({path.stat().st_size / 1024:.1f} KB)")
    print("\nDone. All data is synthetic (Verhoeff/Luhn-valid test values generated at runtime).")


if __name__ == "__main__":
    main()
