import unittest
from unittest.mock import patch

import app as pocket


class RestartTest(unittest.TestCase):
    def setUp(self):
        self.client = pocket.app.test_client()

    def test_restart_command_defaults_to_python_runner(self):
        with patch.dict(pocket.os.environ, {}, clear=True):
            command = pocket.restart_command()

        self.assertIn("run_pocket.py", command)
        self.assertNotIn("-m flask", command)

    def test_restart_command_can_be_overridden(self):
        with patch.dict(pocket.os.environ, {"POCKET_RESTART_COMMAND": "sh run-pocket.sh"}):
            self.assertEqual(pocket.restart_command(), "sh run-pocket.sh")

    def test_restart_page_shows_command_and_log_without_posting(self):
        response = self.client.get("/restart")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("Start a fresh Pocket Server process", html)
        self.assertIn("Command:", html)
        self.assertIn("pocket-restart.log", html)


if __name__ == "__main__":
    unittest.main()
