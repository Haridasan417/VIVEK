# VIVEK

VIVEK is a unified **Scam Intelligence Engine** for India-focused scam patterns where deception is cross-modal (message + link + screenshot).

## What this MVP does (Phase 1)

- Ingests suspicious artifacts from WhatsApp-like flows:
  - chat text
  - links
  - screenshot OCR text
- Auto-detects modality and runs detectors in parallel.
- Produces one explainable output:
  - `risk_score` (0–100)
  - `action`: `Safe` / `Caution` / `High-Risk` / `Block`
  - plain-language reason
- Stores every result to a local feedback DB (`vivek_feedback.db`) to support a learning loop.

## Why this is not a toy

Real scams in India are multi-step and narrative-driven (impersonation + urgency + payment rails like UPI). This MVP focuses on coordinated signals rather than single-file fake/real classification.

## Architecture (implemented)

- **Input layer**: `POST /analyze` accepts message text, URL, screenshot OCR text.
- **Modality engines**:
  - text scam-script heuristics
  - link/domain risk checks (typosquat-like impersonation, suspicious TLD, punycode, non-HTTPS, IP-host links)
  - screenshot text context checks (payment-alert mimicry + scam cues)
- **Fusion layer**:
  - weighted risk fusion + cross-modal correlation bonus
- **Output layer**:
  - score + action + top reason + per-engine scores
- **Feedback loop**:
  - persists analysis metadata in SQLite.

## Product prioritization guidance

Build first:
1. Text + link + screenshot correlation (already here)
2. Explanation quality and false-positive controls
3. Ops visibility (top scam templates, high-risk domains, repeat patterns)

Cut for Round 1:
- Real-time video deepfake inference in production paths
- Full social graph/bot detection
- Heavy partnership integrations (bank/telecom) before MVP signal quality is proven

## Assumptions

- OCR extraction is done by the client before hitting this backend (`screenshot_text` field).
- This MVP is a backend risk engine and can be wrapped by a WhatsApp bot.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

API will be available at `http://127.0.0.1:8000`.

Example:

```bash
curl -X POST http://127.0.0.1:8000/analyze \
  -H 'Content-Type: application/json' \
  -d '{
    "message_text": "Urgent! Complete KYC now and share OTP",
    "url": "http://sbi-kyc-update.xyz/login?verify=1",
    "screenshot_text": "Your account debited. Call 9876543210 now"
  }'
```

## Tests

```bash
python -m unittest discover -s tests -p 'test_*.py' -q
```
