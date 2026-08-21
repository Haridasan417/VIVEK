
VIVEK
VIVEK is a unified Scam Intelligence Engine for India‑focused scam patterns where deception is cross‑modal (message + link + screenshot, with account/social signals scaffolded for Phase 2).

What this build does (Phase 1 MVP + Phase 2 scaffold)
Ingests suspicious artifacts from WhatsApp‑like flows:
chat text, links, screenshot OCR text, and (optionally) audio/video/social metadata.

Auto‑detects modality and runs engines in parallel, with per‑engine timeouts so one slow engine never blocks the response.

Matches content against a seeded scam‑pattern database (TF‑IDF + cosine similarity) covering real Indian scam categories: digital arrest, UPI collect‑request/refund, fake KYC, loan‑app harassment, fake job offers, romance/matrimonial scams, courier/customs scams, OTP phishing.

Fuses everything into one explainable risk_score (0–100), a named reason, and an action: Safe / Caution / High‑Risk / Block.

Has a real WhatsApp Business Cloud API webhook — receives messages, analyzes them, replies automatically.

Persists every analysis to a feedback store (SQLite locally, Postgres in production via DATABASE_URL).

Exposes a /patterns/confirm endpoint so a human reviewer can add a confirmed new scam sample, which the pattern matcher picks up immediately — this is the “learning loop” from the architecture doc, made concrete.

Why heuristics, not trained models
Every engine here is a transparent, explainable rule system, not a black‑box classifier. This is deliberate:

No labeled Indian‑scam corpus yet — a trained model would need one.

Every score must ship with a plain‑language reason; rules make that trivial.

Rules are debuggable live during a demo. If a judge asks “why did this score 60?”, you can point at the exact line of code.

The pattern‑matching layer (patterns.py) is where you’d swap in a real embedding model or a learned fusion model later, once you have confirmed‑outcome data to train on.

Architecture (implemented)
Code
POST /analyze          -> text + link + screenshot + social engines run in parallel
                           -> pattern match against scam-pattern DB
                           -> fusion layer (weighted score + correlation + pattern bonus)
                           -> feedback store (SQLite/Postgres)
POST /webhook/whatsapp -> receives WhatsApp messages, calls /analyze, replies
GET  /webhook/whatsapp -> Meta's webhook verification handshake
GET  /patterns         -> list known scam patterns
POST /patterns/confirm -> add a confirmed sample to a pattern (feedback/learning loop)
GET  /health           -> liveness check
Files:

app.py — FastAPI wiring, /analyze orchestration, WhatsApp webhook route.

engines.py — text, link, screenshot, social heuristic engines.

patterns.py — TF‑IDF scam‑pattern similarity store + seed Indian scam patterns.

fusion.py — weighted score fusion + cross‑modal correlation + pattern bonus.

storage.py — SQLAlchemy feedback store (SQLite or Postgres via DATABASE_URL).

whatsapp.py — WhatsApp Cloud API webhook verify/receive/reply.

schemas.py — Pydantic request/response models.

What is explicitly NOT in this build
These stay on the roadmap slide, not in code, because building them for real in the time available would mean either shipping something that doesn’t actually work, or overclaiming capability:

Real audio/video deepfake detection (needs dataset + GPU serving).

ONNX/TorchServe model serving (no trained models yet).

A real vector DB (pgvector/Pinecone/Weaviate). TF‑IDF suffices for demo scale.

Browser extension, in‑app SDK, bank/telecom partnerships.

Full OCR pipeline inside the WhatsApp bot (marked TODO).

Quick start
bash
python -m venv .venv
# Activate:
# Linux/macOS:
source .venv/bin/activate
# Windows (cmd):
.\.venv\Scripts\activate
# Windows (PowerShell):
.\.venv\Scripts\Activate.ps1

pip install -r requirements.txt
cp .env.example .env        # fill in values as you get them; safe to leave blank locally
python app.py
API available at http://127.0.0.1:8000. Interactive docs at http://127.0.0.1:8000/docs.

Phase 2 runtime config
To enable Phase 2 engines in this scaffold:

powershell
$env:VIVEK_ENABLE_AUDIO_ENGINE="1"
$env:VIVEK_ENABLE_VIDEO_ENGINE="1"
python app.py
Check active Phase 2 runtime config:

powershell
curl http://127.0.0.1:8000/phase2/status
Example: analyze a message
bash
curl -X POST http://127.0.0.1:8000/analyze \
  -H 'Content-Type: application/json' \
  -d '{
    "message_text": "This is CBI officer speaking, your Aadhaar is linked to a parcel containing drugs, you are under digital arrest, stay on video call",
    "source": "whatsapp"
  }'
Example: confirm a new scam sample (feedback loop)
bash
curl -X POST http://127.0.0.1:8000/patterns/confirm \
  -H 'Content-Type: application/json' \
  -d '{"pattern_id": "fake_kyc", "sample_text": "Your electricity connection will be cut tonight, pay now via this link"}'
Deploying to Render with Postgres
Render dashboard → New → PostgreSQL → create a free instance → copy the Internal Database URL.

New → Web Service → connect this repo.

Build command: pip install -r requirements.txt

Start command: uvicorn app:app --host 0.0.0.0 --port $PORT

Environment tab → add DATABASE_URL, WHATSAPP_TOKEN, WHATSAPP_PHONE_NUMBER_ID, WHATSAPP_VERIFY_TOKEN.

Deploy. Every push to main auto‑redeploys.

Wiring up the WhatsApp bot
developers.facebook.com → create an app → add the “WhatsApp” product.

Set WHATSAPP_TOKEN and WHATSAPP_PHONE_NUMBER_ID from that dashboard.

Set WHATSAPP_VERIFY_TOKEN to any string you choose — put the same string in the Meta app’s webhook config.

In the Meta app’s webhook settings, set the callback URL to https://<your-render-url>/webhook/whatsapp and subscribe to the messages field.

The free test number can only message numbers you’ve explicitly added as testers in the Meta dashboard — that’s a Meta sandbox limit, fine for a hackathon demo.

Tests
bash
python -m unittest discover -s tests -p 'test_*.py' -v
21 tests covering: modality detection, fusion scoring, pattern matching, the social engine, WhatsApp payload parsing, and engine‑timeout fallback behavior.

Product prioritization guidance
Build first (this build does all of these):

Text + link + screenshot + social correlation with named pattern explanations.

False‑positive control via transparent, debuggable rules.

A real feedback/learning loop (/patterns/confirm).

Cut for the Grand Finale:

Real‑time video/audio deepfake inference in production paths.

Full social graph/bot detection (needs platform API access).

Bank/telecom partnership integrations.

Assumptions
OCR extraction for screenshots is done by the client before hitting this backend (screenshot_text field).

This is a backend risk engine, wrapped by the WhatsApp bot; a future browser extension or in‑app SDK would call the same /analyze endpoint.