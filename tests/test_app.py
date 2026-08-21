import asyncio
import unittest

import app as app_module
from app import (
    AnalyzeRequest,
    analyze,
    detect_modalities,
    get_phase2_status,
    to_evidence_bundle,
)


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
            audio_transcript="  manager speaking urgently ",
            video_context_text="  deepfake lip sync mismatch ",
            source="whatsapp",
        )
        bundle = to_evidence_bundle(payload)
        self.assertEqual(bundle["text"], "hi there")
        self.assertEqual(bundle["links"], ["https://example.com/login"])
        self.assertEqual(bundle["image_ocr_text"], "fake bank alert")
        self.assertEqual(bundle["audio_transcript"], "manager speaking urgently")
        self.assertEqual(bundle["video_context_text"], "deepfake lip sync mismatch")
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

    def test_phase2_audio_video_disabled_by_default(self):
        payload = AnalyzeRequest(
            audio_transcript="urgent call from bank manager share otp",
            video_context_text="deepfake face swap urgent payment",
        )
        response = asyncio.run(analyze(payload))
        self.assertEqual(response.engine_status.get("audio"), "disabled")
        self.assertEqual(response.engine_status.get("video"), "disabled")

    def test_phase2_audio_video_scoring_when_enabled(self):
        original_audio = app_module.ENABLE_AUDIO_ENGINE
        original_video = app_module.ENABLE_VIDEO_ENGINE
        app_module.ENABLE_AUDIO_ENGINE = True
        app_module.ENABLE_VIDEO_ENGINE = True
        try:
            payload = AnalyzeRequest(
                message_text="transfer now",
                audio_transcript="urgent call from bank manager share otp",
                video_context_text="deepfake face swap urgent payment",
            )
            response = asyncio.run(analyze(payload))
            self.assertGreater(response.engine_scores.get("audio", 0), 0)
            self.assertGreater(response.engine_scores.get("video", 0), 0)
        finally:
            app_module.ENABLE_AUDIO_ENGINE = original_audio
            app_module.ENABLE_VIDEO_ENGINE = original_video

    def test_phase2_status_reports_flags(self):
        original_audio = app_module.ENABLE_AUDIO_ENGINE
        original_video = app_module.ENABLE_VIDEO_ENGINE
        app_module.ENABLE_AUDIO_ENGINE = True
        app_module.ENABLE_VIDEO_ENGINE = False
        try:
            status = get_phase2_status()
            self.assertTrue(status.audio_engine_enabled)
            self.assertFalse(status.video_engine_enabled)
            self.assertGreater(status.engine_timeout_seconds, 0)
        finally:
            app_module.ENABLE_AUDIO_ENGINE = original_audio
            app_module.ENABLE_VIDEO_ENGINE = original_video


if __name__ == "__main__":
    unittest.main()
