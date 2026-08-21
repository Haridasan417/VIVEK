import asyncio
import unittest

import app as app_module
from app import AnalyzeRequest, analyze, detect_modalities, to_evidence_bundle


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
        original_timeout = app_module.ENGINE_TIMEOUT_SECONDS
        original_analyze_text = app_module.analyze_text

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


if __name__ == "__main__":
    unittest.main()
