"""Request/response contracts for the VIVEK API."""
from pydantic import BaseModel, Field


class AnalyzeRequest(BaseModel):
    message_text: str | None = Field(default=None, description="WhatsApp/chat text")
    url: str | None = Field(default=None, description="Suspicious URL")
    screenshot_text: str | None = Field(
        default=None,
        description="OCR extracted text from screenshot (MVP assumes OCR done by client)",
    )
    source: str = Field(default="whatsapp", description="Source channel")

    # --- social/post signals (all optional; social engine only runs if enough are present) ---
    platform: str | None = Field(default=None, description="e.g. instagram, facebook, x, whatsapp_status")
    account_age_days: int | None = Field(default=None, description="Age of the posting account, in days")
    followers_count: int | None = Field(default=None)
    following_count: int | None = Field(default=None)
    posts_count: int | None = Field(default=None)
    bio_text: str | None = Field(default=None, description="Account bio/description text")
    claims_official: bool = Field(
        default=False, description="Account claims to represent a bank/govt/company but is not verified"
    )
    is_verified: bool = Field(default=False)


class PatternMatch(BaseModel):
    pattern_id: str
    name: str
    category: str
    similarity: float  # 0.0 - 1.0


class AnalyzeResponse(BaseModel):
    risk_score: int
    action: str
    reason: str
    modalities: list[str]
    engine_scores: dict[str, int]
    engine_status: dict[str, str]
    matched_pattern: PatternMatch | None = None
