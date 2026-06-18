import tempfile
import unittest
from pathlib import Path
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
                    "filename": "objet-001-original.png",
                    "url": "http://localhost/media/maison-flou/objet-001-original.png",
                    "mime_type": "image/png",
                    "width": 928,
                    "height": 1152,
                    "model": "gemini-3.1-flash-image",
                }):
                    with patch("app.square_maison_flou_image", return_value={
                        "filename": "objet-001-square.jpg",
                        "url": "http://localhost/media/maison-flou/objet-001-square.jpg",
                        "mime_type": "image/jpeg",
                        "width": 1080,
                        "height": 1080,
                        "source_filename": "objet-001-original.png",
                        "quality": 88,
                        "method": "square_screenshot_copy",
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
        self.assertEqual(data["image_source"], "gemini_square")
        self.assertIn("/media/maison-flou/objet-001-square.jpg", data["image_url"])
        self.assertEqual(data["image_width"], 1080)
        self.assertEqual(data["image_height"], 1080)
        self.assertEqual(data["original_image_file"]["filename"], "objet-001-original.png")
        self.assertEqual(data["image_file"]["source_filename"], "objet-001-original.png")
        self.assertEqual(data["image_file"]["method"], "square_screenshot_copy")
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
                            "filename": "objet-009-original.png",
                            "url": "http://localhost/media/maison-flou/objet-009-original.png",
                            "mime_type": "image/png",
                            "width": 928,
                            "height": 1152,
                            "model": "gemini-3.1-flash-image",
                        }):
                            with patch("app.square_maison_flou_image", return_value={
                                "filename": "objet-009-square.jpg",
                                "url": "http://localhost/media/maison-flou/objet-009-square.jpg",
                                "mime_type": "image/jpeg",
                                "width": 1080,
                                "height": 1080,
                                "source_filename": "objet-009-original.png",
                                "quality": 88,
                                "method": "square_screenshot_copy",
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
        self.assertEqual(kwargs["image_url"], "http://localhost/media/maison-flou/objet-009-square.jpg")
        self.assertEqual(kwargs["image_width"], 1080)
        self.assertEqual(kwargs["image_height"], 1080)
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

    def test_square_processor_center_crops_and_reencodes_jpeg(self):
        from PIL import Image

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source_path = temp_path / "source.jpg"
            Image.new("RGB", (80, 100), color=(200, 100, 50)).save(source_path, format="JPEG")

            image_info = {
                "filename": "source.jpg",
                "path": str(source_path),
                "url": "http://localhost/media/maison-flou/source.jpg",
                "mime_type": "image/jpeg",
                "width": 80,
                "height": 100,
                "model": "gemini-3.1-flash-image",
            }

            with patch("app.MAISON_FLOU_IMAGES_DIR", temp_path):
                with patch("app.maison_flou_media_url", side_effect=lambda name: f"http://localhost/media/maison-flou/{name}"):
                    result = pocket.square_maison_flou_image(image_info, size=64, quality=80)

            output_path = temp_path / result["filename"]
            self.assertTrue(output_path.exists())
            self.assertEqual(result["width"], 64)
            self.assertEqual(result["height"], 64)
            self.assertEqual(result["mime_type"], "image/jpeg")
            self.assertEqual(result["method"], "square_screenshot_copy")
            with Image.open(output_path) as output:
                self.assertEqual(output.size, (64, 64))
                self.assertEqual(output.format, "JPEG")


if __name__ == "__main__":
    unittest.main()
