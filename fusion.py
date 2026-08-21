"""Fusion & Correlation Layer.

Deliberately a transparent weighted rule engine, not a learned fusion model —
we have no labeled multi-modal training data yet, and every score must ship
with a plain-language reason. Swap in a learned fusion model later once you
have enough confirmed-outcome feedback data to train one; keep this same
function signature so nothing upstream/downstream has to change.
"""
from engines import EngineResult
from patterns import PatternMatch

SAFE, CAUTION, HIGH_RISK, BLOCK = "Safe", "Caution", "High-Risk", "Block"

BASE_WEIGHTS = {"text": 0.30, "link": 0.35, "screenshot": 0.20, "social": 0.15}


def _action_from_score(score: int) -> str:
    if score >= 75:
        return BLOCK
    if score >= 50:
        return HIGH_RISK
    if score >= 25:
        return CAUTION
    return SAFE


def fuse_results(
    results: dict[str, EngineResult],
    modalities: list[str],
    pattern_match: PatternMatch | None = None,
) -> tuple[int, list[str], dict[str, int], dict[str, str]]:
    scorable_modalities = [m for m in modalities if results[m].status == "ok"]
    present_weight = sum(BASE_WEIGHTS[m] for m in scorable_modalities) or 1
    weighted_score = sum(results[m].score * BASE_WEIGHTS[m] for m in scorable_modalities) / present_weight

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

    if pattern_match is not None:
        # Similarity 0.35-1.0 -> bonus roughly 8-30 points, plus a named, human-legible reason.
        pattern_bonus = int(round(8 + pattern_match.similarity * 22))
        correlation_bonus += pattern_bonus
        reasons.insert(
            0,
            f"Matches known pattern: {pattern_match.name} "
            f"({int(pattern_match.similarity * 100)}% similarity)",
        )

    final_score = min(100, int(round(weighted_score + correlation_bonus)))
    engine_scores = {k: v.score for k, v in results.items() if k in modalities}
    engine_status = {k: v.status for k, v in results.items() if k in modalities}
    return final_score, reasons, engine_scores, engine_status
