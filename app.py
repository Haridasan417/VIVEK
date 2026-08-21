import asyncio
import ipaddress
import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from fastapi import FastAPI
from pydantic import BaseModel, Field


SAFE, CAUTION, HIGH_RISK, BLOCK = "Safe", "Caution", "High-Risk", "Block"

KNOWN_BAD_DOMAINS = {
    "paytm-offer-free.top",
    "sbi-kyc-update.xyz",
    "upi-verify-now.click",
}

SCAM_KEYWORDS = {
    "urgency": ["urgent", "immediately", "act now", "within 10 minutes"],
    "credential": ["share otp", "otp", "pin", "cvv", "password"],
    "financial": ["kyc", "upi", "bank", "refund", "collect request", "reward"],
    "impersonation": ["manager", "police", "income tax", "rbi", "customer care"],
}


class AnalyzeRequest(BaseModel):
    message_text: str | None = Field(default=None, description="WhatsApp/chat text")
    url: str | None = Field(default=None, description="Suspicious URL")
    screenshot_text: str | None = Field(
        default=None,
        description="OCR extracted text from screenshot (MVP assumes OCR done by client)",
    )
    source: str = Field(default="whatsapp", description="Source channel")


class AnalyzeResponse(BaseModel):
    risk_score: int
    action: str
    reason: str
    modalities: list[str]
    engine_scores: dict[str, int]
    engine_status: dict[str, str]


@dataclass
class EngineResult:
    score: int
    reasons: list[str]
    status: str = "ok"


class FeedbackStore:
    def __init__(self, db_path: str = "vivek_feedback.db") -> None:
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS analysis_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    source TEXT NOT NULL,
                    modalities TEXT NOT NULL,
                    score INTEGER NOT NULL,
                    action TEXT NOT NULL,
                    reasons TEXT NOT NULL
                )
                """
            )

    def record(self, source: str, modalities: list[str], score: int, action: str, reasons: list[str]) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO analysis_events(created_at, source, modalities, score, action, reasons)
                VALUES(?, ?, ?, ?, ?, ?)
                """,
                (
                    datetime.now(timezone.utc).isoformat(),
                    source,
                    json.dumps(modalities),
                    score,
                    action,
                    json.dumps(reasons),
                ),
            )


def detect_modalities(payload: AnalyzeRequest) -> list[str]:
    modalities = []
    if payload.message_text:
        modalities.append("text")
    if payload.url:
        modalities.append("link")
    if payload.screenshot_text:
        modalities.append("screenshot")
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


def _keyword_hits(text: str) -> tuple[int, list[str]]:
    normalized = text.lower()
    score = 0
    reasons = []
    for bucket, words in SCAM_KEYWORDS.items():
        hits = [w for w in words if w in normalized]
        if hits:
            score += min(25, 8 * len(hits))
            reasons.append(f"Detected {bucket} cues: {', '.join(hits[:2])}")
    return min(score, 100), reasons


async def analyze_text(message_text: str | None) -> EngineResult:
    if not message_text:
        return EngineResult(score=0, reasons=[])
    score, reasons = _keyword_hits(message_text)
    if re.search(r"\b(send|transfer)\b.*\b(now|immediately)\b", message_text.lower()):
        score = min(100, score + 15)
        reasons.append("Text requests immediate money transfer")
    return EngineResult(score=score, reasons=reasons)


def _is_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


async def analyze_link(url: str | None) -> EngineResult:
    if not url:
        return EngineResult(score=0, reasons=[])

    parsed = urlparse(url if "//" in url else f"https://{url}")
    host = (parsed.hostname or "").lower()
    score = 0
    reasons = []

    if host in KNOWN_BAD_DOMAINS:
        score += 65
        reasons.append("Domain matches known scam patterns")

    if _is_ip(host):
        score += 25
        reasons.append("Link uses raw IP address")

    if host.startswith("xn--"):
        score += 25
        reasons.append("Domain uses punycode (possible homograph)")

    suspicious_tlds = (".xyz", ".top", ".click", ".ru")
    if host.endswith(suspicious_tlds):
        score += 20
        reasons.append("Domain TLD frequently seen in phishing campaigns")

    if parsed.scheme and parsed.scheme.lower() != "https":
        score += 15
        reasons.append("Link is not HTTPS")

    for brand in ("sbi", "hdfc", "icici", "axis", "paytm", "phonepe", "gpay"):
        if brand in host and host not in {f"{brand}.com", f"www.{brand}.com"}:
            score += 15
            reasons.append(f"Domain appears to impersonate {brand.upper()}")
            break

    if any(k in (parsed.query or "").lower() for k in ("redirect", "token", "verify", "kyc")):
        score += 10
        reasons.append("Query contains suspicious phishing parameters")

    return EngineResult(score=min(score, 100), reasons=reasons)


async def analyze_screenshot(screenshot_text: str | None) -> EngineResult:
    if not screenshot_text:
        return EngineResult(score=0, reasons=[])
    score, reasons = _keyword_hits(screenshot_text)
    if any(x in screenshot_text.lower() for x in ["credited", "debited", "collect request"]):
        score = min(100, score + 15)
        reasons.append("Screenshot mimics payment or account alert")
    if re.search(r"\b\d{10}\b", screenshot_text):
        score = min(100, score + 10)
        reasons.append("Contains phone number often used for callback scams")
    return EngineResult(score=score, reasons=reasons)


def _action_from_score(score: int) -> str:
    if score >= 75:
        return BLOCK
    if score >= 50:
        return HIGH_RISK
    if score >= 25:
        return CAUTION
    return SAFE


ENGINE_TIMEOUT_SECONDS = 1.5


async def _run_engine_with_timeout(engine_name: str, coro: Any) -> EngineResult:
    try:
        return await asyncio.wait_for(coro, timeout=ENGINE_TIMEOUT_SECONDS)
    except TimeoutError:
        return EngineResult(
            score=0,
            reasons=[f"{engine_name} timed out and was excluded from scoring"],
            status="timeout",
        )


def fuse_results(
    results: dict[str, EngineResult], modalities: list[str]
) -> tuple[int, list[str], dict[str, int], dict[str, str]]:
    weights = {"text": 0.35, "link": 0.4, "screenshot": 0.25}
    scorable_modalities = [m for m in modalities if results[m].status == "ok"]
    present_weight = sum(weights[m] for m in scorable_modalities) or 1
    weighted_score = sum(results[m].score * weights[m] for m in scorable_modalities) / present_weight

    reasons: list[str] = []
    for m in modalities:
        reasons.extend(results[m].reasons[:2])

    correlation_bonus = 0
    if (
        "text" in scorable_modalities
        and "link" in scorable_modalities
        and results["text"].score >= 45
        and results["link"].score >= 45
    ):
        correlation_bonus += 10
        reasons.append("Text and link jointly indicate coordinated phishing")
    if (
        "text" in scorable_modalities
        and "screenshot" in scorable_modalities
        and results["text"].score >= 40
        and results["screenshot"].score >= 40
    ):
        correlation_bonus += 8
        reasons.append("Text aligns with suspicious payment screenshot")

    final_score = min(100, int(round(weighted_score + correlation_bonus)))
    engine_scores = {k: v.score for k, v in results.items() if k in modalities}
    engine_status = {k: v.status for k, v in results.items() if k in modalities}
    return final_score, reasons, engine_scores, engine_status


feedback_store = FeedbackStore()
app = FastAPI(title="VIVEK Scam Intelligence Engine", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze(payload: AnalyzeRequest) -> AnalyzeResponse:
    bundle = to_evidence_bundle(payload)
    modalities = []
    if bundle["text"]:
        modalities.append("text")
    if bundle["links"]:
        modalities.append("link")
    if bundle["image_ocr_text"]:
        modalities.append("screenshot")
    if not modalities:
        return AnalyzeResponse(
            risk_score=0,
            action=SAFE,
            reason="No analyzable artifact found. Share text, link, or screenshot.",
            modalities=[],
            engine_scores={},
            engine_status={},
        )

    text_result, link_result, screenshot_result = await asyncio.gather(
        _run_engine_with_timeout("text", analyze_text(bundle["text"])),
        _run_engine_with_timeout("link", analyze_link(bundle["links"][0] if bundle["links"] else None)),
        _run_engine_with_timeout("screenshot", analyze_screenshot(bundle["image_ocr_text"])),
    )

    results = {"text": text_result, "link": link_result, "screenshot": screenshot_result}
    score, reasons, engine_scores, engine_status = fuse_results(results, modalities)
    action = _action_from_score(score)
    summary = reasons[0] if reasons else "No high-risk scam indicators detected"

    feedback_store.record(payload.source, modalities, score, action, reasons)

    return AnalyzeResponse(
        risk_score=score,
        action=action,
        reason=summary,
        modalities=modalities,
        engine_scores=engine_scores,
        engine_status=engine_status,
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=False)
