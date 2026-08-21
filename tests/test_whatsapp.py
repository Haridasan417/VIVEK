import unittest

from whatsapp import extract_inbound_message, format_reply


TEXT_PAYLOAD = {
    "entry": [
        {
            "changes": [
                {
                    "value": {
                        "messages": [
                            {"from": "919876543210", "type": "text", "text": {"body": "share your otp now"}}
                        ]
                    }
                }
            ]
        }
    ]
}

IMAGE_PAYLOAD = {
    "entry": [{"changes": [{"value": {"messages": [{"from": "919876543210", "type": "image", "image": {"id": "media123"}}]}}]}]
}

STATUS_PAYLOAD = {"entry": [{"changes": [{"value": {"statuses": [{"id": "wamid.abc"}]}}]}]}


class WhatsAppParsingTests(unittest.TestCase):
    def test_extracts_text_message(self):
        message = extract_inbound_message(TEXT_PAYLOAD)
        self.assertEqual(message["type"], "text")
        self.assertEqual(message["from"], "919876543210")
        self.assertEqual(message["text"], "share your otp now")

    def test_extracts_image_media_id(self):
        message = extract_inbound_message(IMAGE_PAYLOAD)
        self.assertEqual(message["type"], "image")
        self.assertEqual(message["media_id"], "media123")

    def test_status_update_returns_none(self):
        self.assertIsNone(extract_inbound_message(STATUS_PAYLOAD))

    def test_malformed_payload_returns_none(self):
        self.assertIsNone(extract_inbound_message({}))

    def test_format_reply_contains_score_and_action(self):
        reply = format_reply(82, "Block", "Matches known pattern: Digital Arrest")
        self.assertIn("82/100", reply)
        self.assertIn("Block", reply)
        self.assertIn("Digital Arrest", reply)


if __name__ == "__main__":
    unittest.main()
