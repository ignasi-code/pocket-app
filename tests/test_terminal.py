import unittest

import app as pocket


class TerminalPageTest(unittest.TestCase):
    def setUp(self):
        self.original_token = pocket.POCKET_ACCESS_TOKEN
        pocket.POCKET_ACCESS_TOKEN = ""
        self.client = pocket.app.test_client()

    def tearDown(self):
        pocket.POCKET_ACCESS_TOKEN = self.original_token

    def test_terminal_page_is_served(self):
        response = self.client.get("/terminal")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("Pocket Terminal", html)
        self.assertIn("/api/terminal", html)
        self.assertIn("textarea", html)

    def test_terminal_requires_configured_token(self):
        response = self.client.post("/api/terminal", json={"command": "printf hello"})

        self.assertEqual(response.status_code, 403)
        self.assertIn("POCKET_ACCESS_TOKEN", response.get_json()["error"])

    def test_terminal_rejects_wrong_token(self):
        pocket.POCKET_ACCESS_TOKEN = "secret"

        response = self.client.post(
            "/api/terminal",
            json={"command": "printf hello", "token": "wrong"},
        )

        self.assertEqual(response.status_code, 401)

    def test_terminal_executes_multiline_command_with_token(self):
        pocket.POCKET_ACCESS_TOKEN = "secret"

        response = self.client.post(
            "/api/terminal",
            json={
                "command": "cd /tmp\nprintf 'here:'\npwd",
                "token": "secret",
            },
        )

        data = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data["returncode"], 0)
        self.assertIn("here:/tmp", data["output"])

    def test_terminal_api_returns_output_for_failed_command(self):
        pocket.POCKET_ACCESS_TOKEN = "secret"

        response = self.client.post(
            "/api/terminal",
            json={
                "command": "printf 'actual error' >&2\nexit 7",
                "token": "secret",
            },
        )

        data = response.get_json()
        self.assertEqual(response.status_code, 502)
        self.assertEqual(data["returncode"], 7)
        self.assertIn("actual error", data["output"])

    def test_terminal_ui_shows_failed_command_output(self):
        response = self.client.get("/terminal")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        failure_start = html.index("if (!response.ok) {")
        success_start = html.index('output.textContent = data.output || "(Command returned no output.)";')
        failure_script = html[failure_start:success_start]

        self.assertIn("formatTerminalResult(data)", html)
        self.assertIn("output.textContent = formatTerminalResult(data);", failure_script)


if __name__ == "__main__":
    unittest.main()
