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

    def test_axiom_sync_creates_dataset_and_writes_cursor(self):
        calls = []

        def fake_axiom_request(method, path, payload=None):
            calls.append((method, path, payload))
            if method == "GET" and path == "/v2/datasets":
                return {"datasets": []}
            return {"ok": True}

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("app.BUSINESSES_DIR", Path(temp_dir)):
                with patch("app.AXIOM_API_TOKEN", "axiom-token"):
                    with patch("app.AXIOM_DATASET", "maison-flou-office"):
                        with patch("app.axiom_api_request", side_effect=fake_axiom_request):
                            pocket.append_office_activity_event(
                                "maison-flou",
                                "content.published",
                                subject="Objet 013",
                                message="Buffer accepted",
                                timestamp="2026-06-18T08:00:00Z",
                            )

                            result = pocket.sync_office_activity_to_axiom("maison-flou")

                cursor = pocket.read_axiom_cursor("maison-flou")

        self.assertEqual(result["dataset"], "maison-flou-office")
        self.assertTrue(result["created_dataset"])
        self.assertEqual(result["sent"], 1)
        self.assertTrue(cursor["last_event_id"])
        self.assertEqual(calls[0], ("GET", "/v2/datasets", None))
        self.assertEqual(calls[1][0], "POST")
        self.assertEqual(calls[1][1], "/v2/datasets")
        self.assertEqual(calls[2][0], "POST")
        self.assertEqual(calls[2][1], "/v1/datasets/maison-flou-office/ingest")
        self.assertEqual(calls[2][2][0]["event_type"], "content.published")

    def test_axiom_dataset_name_is_valid(self):
        with patch("app.AXIOM_DATASET", "Maison Flou Office!!"):
            self.assertEqual(pocket.axiom_dataset_name("maison-flou"), "maison-flou-office")


if __name__ == "__main__":
    unittest.main()
