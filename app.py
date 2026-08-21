import asyncio
from typing import Any

from fastapi import FastAPI, Request
from pydantic import BaseModel

from engines import EngineResult, analyze_link, analyze_screenshot, analyze_social, analyze_text
from fusion import SAFE, _action_from_score as action_from_score, fuse_results
from patterns import pattern_store
from schemas import AnalyzeRequest, AnalyzeResponse, PatternMatch as PatternMatchSchema
from storage import FeedbackStore
from whatsapp import extract_inbound_message, format_reply, router as whatsapp_router, send_whatsapp_reply

ENGINE_TIMEOUT_SECONDS = 1.5


def detect_modalities(payload: AnalyzeRequest) -> list[str]:
    modalities = []
    if payload.message_text:
        modalities.append("text")
    if payload.url:
        modalities.append("link")
    if payload.screenshot_text:
        modalities.append("screenshot")
    if payload.claims_official or payload.account_age_days is not None or payload.bio_text:
        modalities.append("social")
    return modalities


def to_evidence_bundle(payload: AnalyzeRequest) -> dict[str, Any]:
    text = (payload.message_text or "").strip()
    raw_url = (payload.url or "").strip()
    screenshot_text = (payload.screenshot_text or "").strip()
    normalized_url = raw_url if raw_url else None
    if normalized_url and "://" not in normalized_url:
        normalized_url = f"https://{normalized_url}"

    links = [normalized_url] if normalized_url else []
    return {
        "source": payload.source,
        "text": text or None,
        "links": links,
        "image_ocr_text": screenshot_text or None,
        "metadata": {"ingest_channel": payload.source},
    }


async def _run_engine_with_timeout(engine_name: str, coro: Any) -> EngineResult:
    try:
        return await asyncio.wait_for(coro, timeout=ENGINE_TIMEOUT_SECONDS)
    except TimeoutError:
        return EngineResult(
            score=0,
            reasons=[f"{engine_name} timed out and was excluded from scoring"],
            status="timeout",
        )


feedback_store = FeedbackStore()
app = FastAPI(title="VIVEK Scam Intelligence Engine", version="0.2.0")
app.include_router(whatsapp_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/patterns")
def list_patterns() -> list[dict]:
    return pattern_store.list_patterns()


class ConfirmedPattern(BaseModel):
    pattern_id: str
    sample_text: str


@app.post("/patterns/confirm")
def confirm_pattern(payload: ConfirmedPattern) -> dict[str, bool]:
    """Feedback loop endpoint: a human (QA team / ops reviewer) confirms a real
    scam message and attaches it to a known pattern. The pattern store rebuilds
    immediately, so the next /analyze call benefits from it."""
    added = pattern_store.add_confirmed_sample(payload.pattern_id, payload.sample_text)
    return {"added": added}


async def analyze(payload: AnalyzeRequest) -> AnalyzeResponse:
    bundle = to_evidence_bundle(payload)
    modalities = detect_modalities(payload)

    if not modalities:
        return AnalyzeResponse(
            risk_score=0,
            action=SAFE,
            reason="No analyzable artifact found. Share text, link, screenshot, or account info.",
            modalities=[],
            engine_scores={},
            engine_status={},
        )

    text_result, link_result, screenshot_result, social_result = await asyncio.gather(
        _run_engine_with_timeout("text", analyze_text(bundle["text"])),
        _run_engine_with_timeout("link", analyze_link(bundle["links"][0] if bundle["links"] else None)),
        _run_engine_with_timeout("screenshot", analyze_screenshot(bundle["image_ocr_text"])),
        _run_engine_with_timeout(
            "social",
            analyze_social(
                payload.platform,
                payload.account_age_days,
                payload.followers_count,
                payload.following_count,
                payload.posts_count,
                payload.bio_text,
                payload.claims_official,
                payload.is_verified,
            ),
        ),
    )

    results = {"text": text_result, "link": link_result, "screenshot": screenshot_result, "social": social_result}

    pattern_match = None
    combined_text = " ".join(filter(None, [bundle["text"], bundle["image_ocr_text"]]))
    if combined_text.strip():
        pattern_match = pattern_store.match(combined_text)

    score, reasons, engine_scores, engine_status = fuse_results(results, modalities, pattern_match)
    action = action_from_score(score)
    summary = reasons[0] if reasons else "No high-risk scam indicators detected"

    feedback_store.record(
        payload.source,
        modalities,
        score,
        action,
        reasons,
        matched_pattern_id=pattern_match.pattern_id if pattern_match else None,
    )

    return AnalyzeResponse(
        risk_score=score,
        action=action,
        reason=summary,
        modalities=modalities,
        engine_scores=engine_scores,
        engine_status=engine_status,
        matched_pattern=PatternMatchSchema(**pattern_match.__dict__) if pattern_match else None,
    )


@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze_endpoint(payload: AnalyzeRequest) -> AnalyzeResponse:
    return await analyze(payload)


@app.post("/webhook/whatsapp")
async def receive_whatsapp(request: Request) -> dict[str, str]:
    body = await request.json()
    message = extract_inbound_message(body)
    if message is None:
        return {"status": "ignored"}

    if message["type"] == "text":
        result = await analyze(AnalyzeRequest(message_text=message["text"], source="whatsapp"))
        reply = format_reply(result.risk_score, result.action, result.reason)
        await send_whatsapp_reply(message["from"], reply)
        return {"status": "processed"}

    if message["type"] == "image":
        await send_whatsapp_reply(
            message["from"],
            "Got your screenshot - image analysis via WhatsApp needs OCR wiring "
            "(see whatsapp.py TODO). Forward the text content for now and I'll check it.",
        )
        return {"status": "image_ack_only"}

    return {"status": "unsupported_type"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=False)
