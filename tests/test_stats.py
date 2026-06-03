import unittest
import json
from unittest.mock import patch, MagicMock
import app as pocket

class StatsTest(unittest.TestCase):
    def setUp(self):
        self.original_token = pocket.POCKET_ACCESS_TOKEN
        pocket.POCKET_ACCESS_TOKEN = ""
        self.client = pocket.app.test_client()

    def tearDown(self):
        pocket.POCKET_ACCESS_TOKEN = self.original_token

    def test_stats_page_is_served(self):
        response = self.client.get("/stats")
        try:
            self.assertEqual(response.status_code, 200)
            html = response.get_data(as_text=True)
            self.assertIn("Pocket Stats", html)
            self.assertIn("/api/stats", html)
            self.assertIn("Battery", html)
            self.assertIn("Memory (RAM)", html)
            self.assertIn("Storage", html)
            self.assertIn("System", html)
        finally:
            response.close()

    @patch('app.get_battery_info')
    @patch('app.get_ram_info')
    @patch('app.get_storage_info')
    @patch('app.get_system_info')
    def test_api_stats_returns_json(self, mock_sys, mock_storage, mock_ram, mock_bat):
        mock_bat.return_value = {"percentage": 85, "status": "Discharging", "temperature": 350}
        mock_ram.return_value = {"total": 8000000, "available": 4000000}
        mock_storage.return_value = {"total": 100000000, "used": 50000000, "free": 50000000}
        mock_sys.return_value = {"platform": "Android", "uptime": "10h 5m 2s", "load": [1.0, 0.5, 0.2]}

        response = self.client.get("/api/stats")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        
        self.assertEqual(data["battery"]["percentage"], 85)
        self.assertEqual(data["ram"]["total"], 8000000)
        self.assertEqual(data["storage"]["free"], 50000000)
        self.assertEqual(data["system"]["platform"], "Android")

    @patch('subprocess.run')
    def test_get_battery_info_handles_missing_termux_api(self, mock_run):
        mock_run.side_effect = FileNotFoundError()
        
        from app import get_battery_info
        info = get_battery_info()
        self.assertEqual(info, {"error": "termux-api not installed"})

    @patch('subprocess.run')
    def test_get_battery_info_handles_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="error")
        
        from app import get_battery_info
        info = get_battery_info()
        self.assertEqual(info, {"error": "termux-battery-status failed"})

if __name__ == "__main__":
    unittest.main()
