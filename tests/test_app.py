import asyncio
import unittest

import app as app_module
from app import analyze, detect_modalities, to_evidence_bundle
from schemas import AnalyzeRequest


class VivekTests(unittest.TestCase):
    def test_detect_modalities(self):
        payload = AnalyzeRequest(message_text="hi", url="https://example.com")
        self.assertEqual(detect_modalities(payload), ["text", "link"])

    def test_high_risk_fusion(self):
        payload = AnalyzeRequest(
            message_text="Urgent! Share OTP and transfer now",
            url="http://sbi-kyc-update.xyz/login?verify=1",
            screenshot_text="Your account debited. Call 9876543210 now",
        )
        response = asyncio.run(analyze(payload))
        self.assertGreaterEqual(response.risk_score, 50)
        self.assertIn(response.action, {"High-Risk", "Block"})
        self.assertTrue(response.reason)

    def test_empty_payload(self):
        payload = AnalyzeRequest()
        response = asyncio.run(analyze(payload))
        self.assertEqual(response.risk_score, 0)
        self.assertEqual(response.action, "Safe")

    def test_evidence_bundle_contract(self):
        payload = AnalyzeRequest(
            message_text="  hi there ",
            url="example.com/login",
            screenshot_text="  fake bank alert ",
            source="whatsapp",
        )
        bundle = to_evidence_bundle(payload)
        self.assertEqual(bundle["text"], "hi there")
        self.assertEqual(bundle["links"], ["https://example.com/login"])
        self.assertEqual(bundle["image_ocr_text"], "fake bank alert")
        self.assertEqual(bundle["metadata"]["ingest_channel"], "whatsapp")

    def test_engine_timeout_fallback(self):
        import engines

        original_timeout = app_module.ENGINE_TIMEOUT_SECONDS
        original_analyze_text = engines.analyze_text

        async def slow_text_engine(message_text):
            await asyncio.sleep(0.05)
            return await original_analyze_text(message_text)

        app_module.analyze_text = slow_text_engine
        app_module.ENGINE_TIMEOUT_SECONDS = 0.001
        try:
            payload = AnalyzeRequest(message_text="urgent transfer now")
            response = asyncio.run(analyze(payload))
            self.assertIn("timeout", response.engine_status.values())
        finally:
            app_module.analyze_text = original_analyze_text
            app_module.ENGINE_TIMEOUT_SECONDS = original_timeout

    def test_digital_arrest_pattern_match_boosts_score(self):
        payload = AnalyzeRequest(
            message_text=(
                "This is CBI officer speaking, your Aadhaar is linked to illegal parcel, "
                "you are under digital arrest, stay on video call"
            ),
        )
        response = asyncio.run(analyze(payload))
        self.assertIsNotNone(response.matched_pattern)
        self.assertEqual(response.matched_pattern.pattern_id, "digital_arrest")
        self.assertIn(response.action, {"High-Risk", "Block"})

    def test_social_engine_triggers_on_account_signals(self):
        payload = AnalyzeRequest(
            message_text="Congratulations you are selected, pay a small deposit to unlock withdrawal",
            account_age_days=3,
            followers_count=5,
            following_count=800,
            claims_official=True,
            is_verified=False,
        )
        response = asyncio.run(analyze(payload))
        self.assertIn("social", response.modalities)
        self.assertGreater(response.engine_scores["social"], 0)


if __name__ == "__main__":
    unittest.main()
