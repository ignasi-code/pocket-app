import unittest
from unittest.mock import patch

import app as pocket


class OpsPageTest(unittest.TestCase):
    def setUp(self):
        self.original_token = pocket.POCKET_ACCESS_TOKEN
        pocket.POCKET_ACCESS_TOKEN = "secret"
        self.client = pocket.app.test_client()

    def tearDown(self):
        pocket.POCKET_ACCESS_TOKEN = self.original_token

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

    def test_ops_open_mode_allows_pull_then_restart_without_manual_token(self):
        with patch.dict(pocket.os.environ, {"POCKET_OPS_OPEN": "1"}):
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
                    response = self.client.post("/ops", data={"action": "pull_restart"})

        self.assertEqual(response.status_code, 200)
        run_git_pull.assert_called_once_with()
        restart.assert_called_once_with()
        html = response.get_data(as_text=True)
        self.assertIn("Pull completed in 0.01s.", html)
        self.assertIn("Restart requested", html)


if __name__ == "__main__":
    unittest.main()
