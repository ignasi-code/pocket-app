import unittest
from unittest.mock import patch

import app as pocket


class MaisonFlouContentTest(unittest.TestCase):
    def setUp(self):
        self.original_token = pocket.POCKET_ACCESS_TOKEN
        pocket.POCKET_ACCESS_TOKEN = ""
        self.client = pocket.app.test_client()

    def tearDown(self):
        pocket.POCKET_ACCESS_TOKEN = self.original_token

    def test_content_endpoint_generates_prompt_caption_and_url(self):
        image_prompt = "A structured white leather bag on sun-bleached stone, razor sharp shadows, 35mm grain."
        raw_caption = "Objet d’étude 001.\n\nSpace folds into a quiet edge.\nForm waits without asking."

        with patch("app.read_maison_flou_sequence", return_value=0):
            with patch("app.save_maison_flou_sequence") as save_sequence:
                with patch("app.generate_maison_flou_image", return_value={
                    "filename": "objet-001-test.png",
                    "url": "http://localhost/media/maison-flou/objet-001-test.png",
                    "mime_type": "image/png",
                    "width": 1024,
                    "height": 1024,
                    "model": "gemini-3.1-flash-image",
                }):
                    with patch("app.run_gemini_text", side_effect=[image_prompt, raw_caption]) as run_ai:
                        response = self.client.post("/api/maison-flou/content", json={})

        self.assertEqual(response.status_code, 200)
        data = response.get_json()

        self.assertEqual(data["business_id"], "maison-flou")
        self.assertEqual(data["object_number"], "001")
        self.assertEqual(data["image_prompt"], image_prompt)
        self.assertIn("Objet d’étude 001.", data["caption"])
        self.assertIn("Allocation for Collection 01 is strictly limited.", data["caption"])
        self.assertIn("maisonflou.com", data["caption"])
        self.assertEqual(data["image_source"], "gemini")
        self.assertIn("/media/maison-flou/objet-001-test.png", data["image_url"])
        self.assertEqual(data["image_width"], 1024)
        self.assertEqual(data["image_height"], 1024)
        self.assertEqual(run_ai.call_count, 2)
        save_sequence.assert_called_once_with(1)

    def test_content_endpoint_can_create_buffer_draft(self):
        image_prompt = "A geometric ceramic object against cream plaster, blinding sunlight, Vogue editorial."
        raw_caption = "Objet d’étude 009.\n\nStillness becomes load-bearing.\nThe object edits the room."

        with patch("app.BUFFER_API_KEY", "buffer-key"):
            with patch("app.get_business_buffer_config", return_value={
                "business_id": "maison-flou",
                "organization_id": "org",
                "channel_id": "channel",
                "default_mode": "addToQueue",
                "metadata_service": "instagram",
                "post_type": "post",
            }):
                with patch("app.create_post", return_value={"post": {"id": "draft-id"}}) as create_post:
                    with patch("app.save_maison_flou_sequence") as save_sequence:
                        with patch("app.generate_maison_flou_image", return_value={
                            "filename": "objet-009-test.png",
                            "url": "http://localhost/media/maison-flou/objet-009-test.png",
                            "mime_type": "image/png",
                            "width": 1024,
                            "height": 1024,
                            "model": "gemini-3.1-flash-image",
                        }):
                            with patch("app.run_gemini_text", return_value=raw_caption):
                                response = self.client.post("/api/maison-flou/content", json={
                                    "object_number": 9,
                                    "image_prompt": image_prompt,
                                    "draft_buffer": True,
                                })

        self.assertEqual(response.status_code, 200)
        data = response.get_json()

        self.assertEqual(data["object_number"], "009")
        self.assertEqual(data["buffer"]["channel_id"], "channel")
        self.assertTrue(data["buffer"]["save_to_draft"])
        create_post.assert_called_once()
        kwargs = create_post.call_args.kwargs
        self.assertEqual(kwargs["channel_id"], "channel")
        self.assertEqual(kwargs["image_width"], 1024)
        self.assertEqual(kwargs["image_height"], 1024)
        self.assertTrue(kwargs["save_to_draft"])
        save_sequence.assert_not_called()

    def test_gemini_timeout_with_byte_output_is_json_error(self):
        error = pocket.subprocess.TimeoutExpired(
            cmd=["gemini"],
            timeout=180,
            output=b"partial stdout",
            stderr=b"partial stderr",
        )

        with patch("app.subprocess.run", side_effect=error):
            with self.assertRaises(pocket.GeminiCliError) as context:
                pocket.run_gemini_text("hello")

        self.assertEqual(context.exception.status_code, 504)
        self.assertIn("partial stdout", context.exception.payload["output"])
        self.assertIn("partial stderr", context.exception.payload["output"])


if __name__ == "__main__":
    unittest.main()
