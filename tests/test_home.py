import unittest

import app as pocket


class HomePageTest(unittest.TestCase):
    def setUp(self):
        self.client = pocket.app.test_client()

    def test_root_serves_arcanoid_game(self):
        response = self.client.get("/")

        try:
            self.assertEqual(response.status_code, 200)
            html = response.get_data(as_text=True)
            self.assertIn("<title>Pocket Arkanoid</title>", html)
            self.assertIn('<canvas id="game"', html)
            self.assertIn("data-game-root", html)
        finally:
            response.close()

    def test_bp_serves_previous_root_landing_page(self):
        response = self.client.get("/bp")

        try:
            self.assertEqual(response.status_code, 200)
            html = response.get_data(as_text=True)
            self.assertIn("bp-v2-landing", html)
            self.assertIn("COCUNAT", html)
        finally:
            response.close()

    def test_maison_flou_preview_serves_static_site_and_assets(self):
        response = self.client.get("/maison-flou")

        try:
            self.assertEqual(response.status_code, 200)
            html = response.get_data(as_text=True)
            self.assertIn("<title>MAISON FLOU</title>", html)
            self.assertIn("/assets/objects/object-010.webp", html)
        finally:
            response.close()

        asset_response = self.client.get("/assets/objects/object-010.webp")
        try:
            self.assertEqual(asset_response.status_code, 200)
            self.assertEqual(asset_response.content_type, "image/webp")
        finally:
            asset_response.close()


if __name__ == "__main__":
    unittest.main()
