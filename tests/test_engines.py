import asyncio
import unittest

from engines import analyze_social


class SocialEngineTests(unittest.TestCase):
    def test_skipped_when_no_signals_present(self):
        result = asyncio.run(analyze_social(None, None, None, None, None, None, False, False))
        self.assertEqual(result.status, "skipped")
        self.assertEqual(result.score, 0)

    def test_new_account_flagged(self):
        result = asyncio.run(analyze_social(None, 2, None, None, None, None, False, False))
        self.assertGreater(result.score, 0)
        self.assertTrue(any("recently" in r for r in result.reasons))

    def test_bot_like_follow_ratio_flagged(self):
        result = asyncio.run(analyze_social(None, None, 5, 900, None, None, False, False))
        self.assertGreater(result.score, 0)
        self.assertTrue(any("ratio" in r for r in result.reasons))

    def test_unverified_official_claim_flagged(self):
        result = asyncio.run(analyze_social(None, None, None, None, None, None, True, False))
        self.assertGreaterEqual(result.score, 30)

    def test_verified_official_claim_not_flagged_for_that_reason(self):
        result = asyncio.run(analyze_social(None, None, None, None, None, None, True, True))
        self.assertFalse(any("without verification" in r for r in result.reasons))


if __name__ == "__main__":
    unittest.main()
