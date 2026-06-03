import unittest

import app as pocket


class FastPageTest(unittest.TestCase):
    def setUp(self):
        self.original_token = pocket.POCKET_ACCESS_TOKEN
        pocket.POCKET_ACCESS_TOKEN = ""
        self.client = pocket.app.test_client()

    def tearDown(self):
        pocket.POCKET_ACCESS_TOKEN = self.original_token

    def test_fast_page_is_served(self):
        response = self.client.get("/fast")

        try:
            self.assertEqual(response.status_code, 200)
            html = response.get_data(as_text=True)
            self.assertIn("Pocket Fast", html)
            self.assertIn("/fast/api/download", html)
            self.assertIn("/fast/api/upload", html)
        finally:
            response.close()

    def test_download_endpoint_streams_requested_bytes(self):
        response = self.client.get("/fast/api/download?bytes=1024")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1024)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertEqual(response.headers["Content-Type"], "application/octet-stream")

    def test_download_ui_starts_activity_meter_before_fetch_wait(self):
        response = self.client.get("/fast")

        try:
            html = response.get_data(as_text=True)
            download_start = html.index("async function runDownloadTest()")
            upload_start = html.index("async function runUploadTest()")
            download_script = html[download_start:upload_start]
            self.assertIn('const stopActivity = startActivityMeter("download");', download_script)
            self.assertIn("await downloadWithProgress(url", download_script)
            meter_start = download_script.index('const stopActivity = startActivityMeter("download");')
            download_wait = download_script.index("await downloadWithProgress(url")

            self.assertIn("function startActivityMeter(kind)", html)
            self.assertIn("function downloadWithProgress(url, onProgress)", html)
            self.assertIn("stopActivity();", download_script)
            self.assertLess(meter_start, download_wait)
        finally:
            response.close()

    def test_upload_endpoint_reports_received_bytes(self):
        payload = b"speed-test" * 128

        response = self.client.post(
            "/fast/api/upload",
            data=payload,
            content_type="application/octet-stream",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["bytes"], len(payload))

    def test_speed_endpoints_require_token_when_configured(self):
        pocket.POCKET_ACCESS_TOKEN = "secret"

        denied = self.client.get("/fast/api/download?bytes=16")
        allowed = self.client.post(
            "/fast/api/upload",
            data=b"ok",
            content_type="application/octet-stream",
            headers={"X-Pocket-Token": "secret"},
        )

        self.assertEqual(denied.status_code, 401)
        self.assertEqual(allowed.status_code, 200)


if __name__ == "__main__":
    unittest.main()
