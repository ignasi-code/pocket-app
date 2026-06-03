import unittest
from unittest.mock import patch

import app as pocket


class GptPageTest(unittest.TestCase):
    def setUp(self):
        self.client = pocket.app.test_client()

    def test_gpt_page_types_successful_output_instead_of_dumping_it(self):
        response = self.client.get("/gpt")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        success_start = html.index('if (!response.ok) {')
        catch_start = html.index("} catch (error) {")
        success_script = html[success_start:catch_start]

        self.assertIn("function stopTyping()", html)
        self.assertIn("async function typeOutput(text)", html)
        self.assertIn('output.classList.add("typing");', html)
        self.assertIn("await typeOutput(data.output ||", success_script)
        self.assertNotIn("output.textContent = data.output", success_script)

    def test_gpt_page_exposes_raw_http_response(self):
        response = self.client.get("/gpt")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)

        self.assertIn('id="raw-toggle"', html)
        self.assertIn('id="raw-output"', html)
        self.assertIn("function setRawResponse(details)", html)
        self.assertIn("function parseJsonResponse(text)", html)
        self.assertIn("const responseText = await response.text();", html)
        self.assertIn("setRawResponse({", html)
        self.assertNotIn("await response.json()", html)

    def test_gemini_extra_args_are_appended_after_model_arg(self):
        with patch.dict(
            pocket.os.environ,
            {
                "POCKET_GEMINI_MODEL": "gemini-test-model",
                "POCKET_GEMINI_ARGS": "--yolo --no-sandbox",
            },
        ):
            self.assertEqual(
                pocket.current_gemini_args(),
                ["-m", "gemini-test-model", "--yolo", "--no-sandbox"],
            )


if __name__ == "__main__":
    unittest.main()
