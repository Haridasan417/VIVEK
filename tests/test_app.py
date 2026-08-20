import asyncio
import unittest

from app import AnalyzeRequest, analyze, detect_modalities


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


if __name__ == "__main__":
    unittest.main()
