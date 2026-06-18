import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app as pocket


class OfficeActivityTest(unittest.TestCase):
    def setUp(self):
        self.original_token = pocket.POCKET_ACCESS_TOKEN
        pocket.POCKET_ACCESS_TOKEN = ""
        self.client = pocket.app.test_client()

    def tearDown(self):
        pocket.POCKET_ACCESS_TOKEN = self.original_token

    def test_activity_log_status_counts_and_latest_actions(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("app.BUSINESSES_DIR", Path(temp_dir)):
                pocket.append_office_activity_event(
                    "maison-flou",
                    "content.generated",
                    subject="Objet 013",
                    message="Image generated",
                    timestamp="2026-06-18T08:00:00Z",
                )
                pocket.append_office_activity_event(
                    "maison-flou",
                    "content.published",
                    subject="Objet 013",
                    message="Buffer accepted",
                    timestamp="2026-06-18T08:03:00Z",
                )
                pocket.append_office_activity_event(
                    "maison-flou",
                    "lead.created",
                    subject="Lead 001",
                    message="Waitlist signup",
                    timestamp="2026-06-18T08:05:00Z",
                )

                response = self.client.get("/api/office/maison-flou/status?day=2026-06-18")

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["status"], "Running normally")
        self.assertEqual(data["event_count"], 3)
        self.assertEqual(data["counts"]["generated"], 1)
        self.assertEqual(data["counts"]["published"], 1)
        self.assertEqual(data["counts"]["leads"], 1)
        self.assertEqual(data["latest_events"][0]["subject"], "Lead 001")

    def test_activity_api_requires_token_when_configured(self):
        pocket.POCKET_ACCESS_TOKEN = "secret"
        response = self.client.post("/api/office/maison-flou/activity", json={
            "event_type": "content.generated",
            "subject": "Objet 013",
        })
        self.assertEqual(response.status_code, 401)

    def test_tldr_uses_fallback_when_ai_fails(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("app.BUSINESSES_DIR", Path(temp_dir)):
                pocket.append_office_activity_event(
                    "maison-flou",
                    "content.published",
                    subject="Objet 013",
                    message="Buffer accepted",
                    timestamp=pocket.office_utc_timestamp(),
                )
                with patch("app.run_gemini_text", side_effect=pocket.GeminiCliError("no ai")):
                    response = self.client.get("/api/office/maison-flou/tldr")

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["source"], "fallback")
        self.assertIn("published", data["text"])


if __name__ == "__main__":
    unittest.main()
