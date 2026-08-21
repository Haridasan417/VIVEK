# VIVEK

VIVEK is a unified **Scam Intelligence Engine** for India-focused scam patterns where
deception is cross-modal (message + link + screenshot + account signals).

## What this build does

- Ingests suspicious artifacts from WhatsApp-like flows: chat text, links, screenshot
  OCR text, and (optionally) social/account metadata.
- Auto-detects modality and runs all applicable engines in parallel, with a per-engine
  timeout so one slow engine never blocks the response.
- Matches text/screenshot content against a **seeded scam-pattern database**
  (TF-IDF + cosine similarity) covering real Indian scam categories: digital arrest,
  UPI collect-request/refund, fake KYC, loan-app harassment, fake job offers,
  romance/matrimonial scams, courier-customs scams, OTP phishing.
- Fuses everything into one explainable `risk_score` (0–100), a named reason, and an
  `action`: `Safe` / `Caution` / `High-Risk` / `Block`.
- Has a real **WhatsApp Business (Cloud API) webhook** — receives messages, analyzes
  them, replies automatically.
- Persists every analysis to a **feedback store** (SQLite locally, Postgres in
  production via `DATABASE_URL`) and exposes a `/patterns/confirm` endpoint so a human
  reviewer can add a confirmed new scam sample, which the pattern matcher picks up
  immediately — this is the "learning loop" from the architecture doc, made concrete.

## Why heuristics, not trained models

Every engine here is a transparent, explainable rule system, not a black-box classifier.
This is a deliberate choice, not a shortcut we forgot to fix:

1. We have no labeled Indian-scam training corpus yet — a trained model would need one.
2. Every score must ship with a plain-language reason; rules make that trivial, a
   trained classifier makes it a research problem (SHAP/LIME-style explainability).
3. Rules are debuggable live during a demo. If a judge asks "why did this score 60?",
   you can point at the exact line of code.

The pattern-matching layer (`patterns.py`) is where you'd swap in a real embedding
model or a learned fusion model later, once you have real confirmed-outcome data to
train on — the function signatures (`match`, `fuse_results`) are built so that swap
doesn't ripple through the rest of the codebase.

## Architecture (implemented in this build)

```
POST /analyze          -> text + link + screenshot + social engines run in parallel
                           -> pattern match against scam-pattern DB
                           -> fusion layer (weighted score + correlation + pattern bonus)
                           -> feedback store (SQLite/Postgres)
POST /webhook/whatsapp  -> receives WhatsApp messages, calls /analyze, replies
GET  /webhook/whatsapp  -> Meta's webhook verification handshake
GET  /patterns          -> list known scam patterns
POST /patterns/confirm  -> add a confirmed sample to a pattern (feedback/learning loop)
GET  /health            -> liveness check
```

Files:
- `app.py` — FastAPI wiring, `/analyze` orchestration, WhatsApp webhook route.
- `engines.py` — text, link, screenshot, social heuristic engines.
- `patterns.py` — TF-IDF scam-pattern similarity store + seed Indian scam patterns.
- `fusion.py` — weighted score fusion + cross-modal correlation + pattern bonus.
- `storage.py` — SQLAlchemy feedback store (SQLite or Postgres via `DATABASE_URL`).
- `whatsapp.py` — WhatsApp Cloud API webhook verify/receive/reply.
- `schemas.py` — Pydantic request/response models.

## What is explicitly NOT in this build (and why)

These stay on the roadmap slide, not in code, because building them for real in the
time available would mean either shipping something that doesn't actually work, or
overclaiming capability to judges evaluating a fraud-detection tool:

- **Real audio/video deepfake detection.** Needs a trained CNN/temporal model, a
  labeled dataset, and GPU serving — not achievable to a real standard on this
  timeline. WhatsApp's re-compression also degrades the exact artifacts these models
  key on, which is a genuine open research problem, not just an engineering gap.
  Pitch it as: "architecture has a modality-engine slot ready for this; Phase 2."
- **ONNX/TorchServe model serving.** No trained models yet to serve.
- **A real vector DB (pgvector/Pinecone/Weaviate).** TF-IDF does the same job for a
  demo-scale pattern set without the deployment overhead; swap it in once pattern
  count and semantic-matching needs outgrow TF-IDF.
- **Browser extension, in-app SDK, bank/telecom partnerships.** Distribution-phase
  work; needs partnerships that can't be secured on a hackathon timeline.
- **Full OCR pipeline inside the WhatsApp bot.** Image messages are detected and the
  media ID is extracted (see `whatsapp.py`), but downloading the image + running OCR
  is left as a marked `TODO` — a real, scoped task for whoever owns it next, not
  silently faked.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # fill in values as you get them; safe to leave blank locally
python app.py
```

API available at `http://127.0.0.1:8000`. Interactive docs at `http://127.0.0.1:8000/docs`.

### Example: analyze a message

```bash
curl -X POST http://127.0.0.1:8000/analyze \
  -H 'Content-Type: application/json' \
  -d '{
    "message_text": "This is CBI officer speaking, your Aadhaar is linked to a parcel containing drugs, you are under digital arrest, stay on video call",
    "source": "whatsapp"
  }'
```

### Example: confirm a new scam sample (feedback loop)

```bash
curl -X POST http://127.0.0.1:8000/patterns/confirm \
  -H 'Content-Type: application/json' \
  -d '{"pattern_id": "fake_kyc", "sample_text": "Your electricity connection will be cut tonight, pay now via this link"}'
```

## Deploying to Render with Postgres

1. Render dashboard -> New -> PostgreSQL -> create a free instance -> copy the
   **Internal Database URL**.
2. New -> Web Service -> connect this repo.
   - Build command: `pip install -r requirements.txt`
   - Start command: `uvicorn app:app --host 0.0.0.0 --port $PORT`
3. Environment tab -> add `DATABASE_URL` (the Postgres URL from step 1),
   `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_VERIFY_TOKEN`.
4. Deploy. Every push to `main` auto-redeploys.

## Wiring up the WhatsApp bot

1. developers.facebook.com -> create an app -> add the "WhatsApp" product. You get a
   free test phone number, a temporary access token, and a Phone Number ID.
2. Set `WHATSAPP_TOKEN` and `WHATSAPP_PHONE_NUMBER_ID` from that dashboard.
3. Set `WHATSAPP_VERIFY_TOKEN` to any string you choose — put the same string in the
   Meta app's webhook config.
4. In the Meta app's webhook settings, set the callback URL to
   `https://<your-render-url>/webhook/whatsapp` and subscribe to the `messages` field.
5. The free test number can only message numbers you've explicitly added as testers in
   the Meta dashboard — that's a Meta sandbox limit, not a bug here, and it's fine for
   a hackathon demo.

## Tests

```bash
python -m unittest discover -s tests -p 'test_*.py' -v
```

21 tests covering: modality detection, fusion scoring, pattern matching, the social
engine, WhatsApp payload parsing, and engine-timeout fallback behavior.

## Product prioritization guidance

Build first (this build does all of these):
1. Text + link + screenshot + social correlation with named pattern explanations.
2. False-positive control via transparent, debuggable rules over black-box scoring.
3. A real feedback/learning loop (`/patterns/confirm`) so ops can improve matching
   without a redeploy.

Cut for the Grand Finale:
- Real-time video/audio deepfake inference in production paths.
- Full social graph/bot detection (this build does account-metadata heuristics, not
  graph analysis — that needs platform API access we don't have).
- Bank/telecom partnership integrations.

## Assumptions

- OCR extraction for screenshots is done by the client before hitting this backend
  (`screenshot_text` field) — no OCR model is bundled in this build.
- This is a backend risk engine, wrapped by the WhatsApp bot; a future browser
  extension or in-app SDK would call the same `/analyze` endpoint.
