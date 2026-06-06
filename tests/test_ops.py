import unittest
import hashlib
import hmac
import time
from unittest.mock import patch

import app as pocket


class OpsPageTest(unittest.TestCase):
    def setUp(self):
        self.original_token = pocket.POCKET_ACCESS_TOKEN
        self.original_hmac_secret = pocket.OPS_HMAC_SECRET
        pocket.POCKET_ACCESS_TOKEN = "secret"
        pocket.OPS_HMAC_SECRET = "ops-hmac-secret"
        self.client = pocket.app.test_client()

    def tearDown(self):
        pocket.POCKET_ACCESS_TOKEN = self.original_token
        pocket.OPS_HMAC_SECRET = self.original_hmac_secret

    def signed_ops_headers(self, body, timestamp=None, secret="ops-hmac-secret"):
        timestamp = str(timestamp or int(time.time()))
        message = b"\n".join([
            b"POST",
            b"/ops",
            timestamp.encode("utf-8"),
            body,
        ])
        signature = hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()
        return {
            "X-Pocket-Ops-Timestamp": timestamp,
            "X-Pocket-Ops-Signature": f"sha256={signature}",
        }

    def test_ops_page_shows_unlock_when_token_is_configured(self):
        response = self.client.get("/ops")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("Pocket Ops", html)
        self.assertIn("Pocket access token", html)
        self.assertIn("Unlock ops", html)

    def test_ops_rejects_wrong_token_for_actions(self):
        response = self.client.post("/ops", data={"action": "pull", "token": "wrong"})

        self.assertEqual(response.status_code, 401)
        self.assertIn("Invalid Pocket access token", response.get_data(as_text=True))

    def test_ops_unlock_sets_session_cookie_and_allows_pull_without_token(self):
        unlock = self.client.post("/ops", data={"action": "unlock", "token": "secret"})

        self.assertEqual(unlock.status_code, 200)
        self.assertIn("pocket_ops_session=", unlock.headers.get("Set-Cookie", ""))

        with patch(
            "app.run_git_pull",
            create=True,
            return_value={
                "elapsed": 0.01,
                "message": "Pull completed in 0.01s.",
                "ok": True,
                "output": "Already up to date.",
                "returncode": 0,
            },
        ) as run_git_pull:
            response = self.client.post("/ops", data={"action": "pull"})

        self.assertEqual(response.status_code, 200)
        run_git_pull.assert_called_once_with()
        self.assertIn("Already up to date.", response.get_data(as_text=True))

    def test_ops_hmac_allows_pull_then_restart_without_manual_token(self):
        body = b"action=pull_restart"
        headers = self.signed_ops_headers(body)

        with patch(
            "app.run_git_pull",
            create=True,
            return_value={
                "elapsed": 0.01,
                "message": "Pull completed in 0.01s.",
                "ok": True,
                "output": "Fast-forward",
                "returncode": 0,
            },
        ) as run_git_pull:
            with patch("app.restart_current_process", return_value="python run_pocket.py") as restart:
                response = self.client.post(
                    "/ops",
                    data=body,
                    content_type="application/x-www-form-urlencoded",
                    headers=headers,
                )

        self.assertEqual(response.status_code, 200)
        run_git_pull.assert_called_once_with()
        restart.assert_called_once_with()
        html = response.get_data(as_text=True)
        self.assertIn("Pull completed in 0.01s.", html)
        self.assertIn("Restart requested", html)

    def test_ops_hmac_rejects_stale_timestamp(self):
        body = b"action=pull"
        headers = self.signed_ops_headers(body, timestamp=int(time.time()) - 600)

        response = self.client.post(
            "/ops",
            data=body,
            content_type="application/x-www-form-urlencoded",
            headers=headers,
        )

        self.assertEqual(response.status_code, 401)
        self.assertIn("Invalid ops signature", response.get_data(as_text=True))

    def test_ops_hmac_rejects_bad_signature(self):
        body = b"action=pull"
        headers = self.signed_ops_headers(body, secret="wrong-secret")

        response = self.client.post(
            "/ops",
            data=body,
            content_type="application/x-www-form-urlencoded",
            headers=headers,
        )

        self.assertEqual(response.status_code, 401)
        self.assertIn("Invalid ops signature", response.get_data(as_text=True))

    def test_ops_open_mode_no_longer_allows_public_actions(self):
        with patch.dict(pocket.os.environ, {"POCKET_OPS_OPEN": "1"}):
            response = self.client.post("/ops", data={"action": "pull"})

        self.assertEqual(response.status_code, 401)
        self.assertIn("Invalid ops signature", response.get_data(as_text=True))

    def test_ops_rejects_legacy_open_mode_actions_after_unlock(self):
        response = self.client.post(
            "/ops",
            data={"action": "enable_open", "token": "secret"},
        )

        self.assertEqual(response.status_code, 410)
        self.assertIn("Open mode has been replaced by HMAC", response.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
