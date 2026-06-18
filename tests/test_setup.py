import unittest
from unittest.mock import patch

import app as pocket


class SetupPageTest(unittest.TestCase):
    def setUp(self):
        self.original_token = pocket.POCKET_ACCESS_TOKEN
        self.client = pocket.app.test_client()

    def tearDown(self):
        pocket.POCKET_ACCESS_TOKEN = self.original_token

    def test_setup_renders_external_service_fields(self):
        pocket.POCKET_ACCESS_TOKEN = ""
        with patch("app.setup_is_open", return_value=True):
            response = self.client.get("/setup")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("axiom_api_token", html)
        self.assertIn("axiom_dataset", html)
        self.assertIn("cloudflare_api_token", html)
        self.assertIn("cloudflare_account_id", html)
        self.assertIn("cloudflare_zone_id", html)
        self.assertIn("cloudflare_pages_project", html)
        self.assertIn("cloudflare_pages_domain", html)
        self.assertIn("cloudflare_pages_output_dir", html)

    def test_setup_saves_external_service_config(self):
        pocket.POCKET_ACCESS_TOKEN = ""

        with patch("app.setup_is_open", return_value=True):
            with patch("app.has_gemini_api_key", return_value=True):
                with patch("app.write_env_updates") as write_env:
                    with patch("app.refresh_runtime_config") as refresh_config:
                        response = self.client.post("/setup", data={
                            "gemini_model": "gemini-2.5-flash-lite",
                            "gemini_args": "",
                            "buffer_organization_id": "",
                            "buffer_channel_id": "",
                            "uptimerobot_status_page_url": "",
                            "uptimerobot_badge_url": "",
                            "axiom_api_token": "axiom-secret",
                            "axiom_dataset": "maison-flou-office",
                            "cloudflare_api_token": "cf-secret",
                            "cloudflare_account_id": "account-id",
                            "cloudflare_zone_id": "zone-id",
                            "cloudflare_pages_project": "maison-flou",
                            "cloudflare_pages_domain": "maisonflou.com",
                            "cloudflare_pages_output_dir": "sites/maison-flou",
                        })

        self.assertEqual(response.status_code, 200)
        updates = write_env.call_args.args[0]
        self.assertEqual(updates["AXIOM_API_TOKEN"], "axiom-secret")
        self.assertEqual(updates["AXIOM_DATASET"], "maison-flou-office")
        self.assertEqual(updates["CLOUDFLARE_API_TOKEN"], "cf-secret")
        self.assertEqual(updates["CLOUDFLARE_ACCOUNT_ID"], "account-id")
        self.assertEqual(updates["CLOUDFLARE_ZONE_ID"], "zone-id")
        self.assertEqual(updates["CLOUDFLARE_PAGES_PROJECT"], "maison-flou")
        self.assertEqual(updates["CLOUDFLARE_PAGES_DOMAIN"], "maisonflou.com")
        self.assertEqual(updates["CLOUDFLARE_PAGES_OUTPUT_DIR"], "sites/maison-flou")
        refresh_config.assert_called_once()


if __name__ == "__main__":
    unittest.main()
