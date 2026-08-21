"""Modality engines. Each engine is a pure async function returning an EngineResult.

These are transparent, rule-based heuristics by design (not black-box ML), because:
1. We have no labeled Indian-scam training data yet.
2. Explainability is a hard product requirement (every score needs a plain-language reason).
3. Rules are debuggable and demoable under hackathon time pressure; they can be swapped
   for trained classifiers later without changing the fusion/API contract.
"""
import ipaddress
import re
from dataclasses import dataclass, field
from urllib.parse import urlparse


@dataclass
class EngineResult:
    score: int
    reasons: list[str] = field(default_factory=list)
    status: str = "ok"  # "ok" | "timeout" | "skipped"


SCAM_KEYWORDS = {
    "urgency": ["urgent", "immediately", "act now", "within 10 minutes", "expires today"],
    "credential": ["share otp", "otp", "pin", "cvv", "password"],
    "financial": ["kyc", "upi", "bank", "refund", "collect request", "reward", "cashback", "aadhaar", "parcel"],
    "impersonation": ["manager", "police", "income tax", "rbi", "customer care", "cbi", "customs", "trai"],
    "fear": [
        "arrest warrant",
        "legal action",
        "case filed",
        "your parcel is seized",
        "account suspended",
        "digital arrest",
        "under arrest",
        "do not disconnect",
    ],
}

KNOWN_BAD_DOMAINS = {
    "paytm-offer-free.top",
    "sbi-kyc-update.xyz",
    "upi-verify-now.click",
}

IMPERSONATED_BRANDS = ("sbi", "hdfc", "icici", "axis", "paytm", "phonepe", "gpay", "rbi", "uidai")


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
        return EngineResult(score=0)
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
        return EngineResult(score=0)

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

    for brand in IMPERSONATED_BRANDS:
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
        return EngineResult(score=0)
    score, reasons = _keyword_hits(screenshot_text)
    if any(x in screenshot_text.lower() for x in ["credited", "debited", "collect request"]):
        score = min(100, score + 15)
        reasons.append("Screenshot mimics payment or account alert")
    if re.search(r"\b\d{10}\b", screenshot_text):
        score = min(100, score + 10)
        reasons.append("Contains phone number often used for callback scams")
    return EngineResult(score=score, reasons=reasons)


async def analyze_social(
    platform: str | None,
    account_age_days: int | None,
    followers_count: int | None,
    following_count: int | None,
    posts_count: int | None,
    bio_text: str | None,
    claims_official: bool,
    is_verified: bool,
) -> EngineResult:
    """Heuristic bot/impersonation-likelihood score from account metadata.

    Deliberately does NOT try to be a "bot detector" in the ML sense (that needs a
    labeled dataset and a real graph/behavioral model we don't have). It flags the
    concrete, explainable red flags that matter for scam accounts specifically:
    brand-new accounts, followers/following imbalance typical of bot farms, and
    unverified accounts claiming official status.
    """
    has_signal = any(
        v is not None
        for v in (account_age_days, followers_count, following_count, posts_count, bio_text)
    ) or claims_official

    if not has_signal:
        return EngineResult(score=0, status="skipped")

    score = 0
    reasons = []

    if account_age_days is not None and account_age_days < 30:
        score += 25
        reasons.append(f"Account created recently ({account_age_days} days ago)")

    if followers_count is not None and following_count is not None:
        if following_count > 200 and followers_count < max(10, following_count // 20):
            score += 20
            reasons.append("Follower/following ratio typical of bot-farm accounts")

    if posts_count is not None and posts_count <= 2 and (followers_count or 0) > 50:
        score += 10
        reasons.append("Very few posts relative to follower count")

    if claims_official and not is_verified:
        score += 30
        reasons.append("Claims official/brand affiliation without verification")

    if bio_text:
        bio_score, bio_reasons = _keyword_hits(bio_text)
        if bio_score:
            score += min(15, bio_score // 3)
            reasons.extend(bio_reasons[:1])

    return EngineResult(score=min(score, 100), reasons=reasons)
