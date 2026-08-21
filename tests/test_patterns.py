import unittest

from patterns import PatternStore


class PatternStoreTests(unittest.TestCase):
    def test_matches_seeded_digital_arrest_pattern(self):
        store = PatternStore()
        match = store.match(
            "CBI officer here, your account is linked to money laundering, stay on this call or face arrest"
        )
        self.assertIsNotNone(match)
        self.assertEqual(match.pattern_id, "digital_arrest")
        self.assertGreater(match.similarity, 0.35)

    def test_no_match_for_unrelated_text(self):
        store = PatternStore()
        match = store.match("Hey, are we still meeting for lunch tomorrow at noon?")
        self.assertIsNone(match)

    def test_add_confirmed_sample_improves_future_matches(self):
        store = PatternStore()
        novel_text = "Your electricity bill payment failed, connection will be cut tonight, pay via this link"
        # This shouldn't match any seed pattern well.
        self.assertIsNone(store.match(novel_text, threshold=0.5))

        added = store.add_confirmed_sample("fake_kyc", novel_text)
        self.assertTrue(added)

        # Now an exact repeat of the confirmed text should match with high similarity.
        match = store.match(novel_text, threshold=0.5)
        self.assertIsNotNone(match)
        self.assertEqual(match.pattern_id, "fake_kyc")

    def test_add_confirmed_sample_unknown_pattern_id_returns_false(self):
        store = PatternStore()
        added = store.add_confirmed_sample("does_not_exist", "some text")
        self.assertFalse(added)


if __name__ == "__main__":
    unittest.main()
