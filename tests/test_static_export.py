import shutil
import unittest

import app as pocket
from scripts.export_pages import build_dist


class StaticExportTest(unittest.TestCase):
    def setUp(self):
        self.output_dir = pocket.BASE_DIR / "tmp-test-dist"
        if self.output_dir.exists():
            shutil.rmtree(self.output_dir)

    def tearDown(self):
        if self.output_dir.exists():
            shutil.rmtree(self.output_dir)

    def test_build_dist_exports_pages_project_routes(self):
        written = build_dist(self.output_dir)

        self.assertIn(self.output_dir / "index.html", written)
        self.assertIn(self.output_dir / "bp" / "index.html", written)
        self.assertIn(self.output_dir / "store" / "index.html", written)
        self.assertIn(self.output_dir / "store" / "cart" / "index.html", written)
        self.assertIn(
            self.output_dir / "store" / "collections" / "new-arrivals" / "index.html",
            written,
        )
        self.assertIn(
            self.output_dir / "store" / "products" / "the-cylinder-cord-necklace-cloud-blue" / "index.html",
            written,
        )
        self.assertIn(self.output_dir / "store" / "catalog.json", written)
        self.assertIn(self.output_dir / "_headers", written)
        self.assertIn(self.output_dir / "robots.txt", written)

        html = (self.output_dir / "store" / "index.html").read_text(encoding="utf-8")
        self.assertIn("Pocket Store", html)
        self.assertIn("/store/assets/store.home.min.css", html)
        self.assertIn('data-store-base-url="https://roxanneassoulin.com"', html)
        self.assertIn('href="https://roxanneassoulin.com/cart" data-checkout', html)
        self.assertNotIn('data-checkout-endpoint="/store/api/checkout"', html)

        robots = (self.output_dir / "robots.txt").read_text(encoding="utf-8")
        self.assertIn("User-agent: *", robots)
        self.assertIn("Allow: /", robots)
        self.assertNotIn("<html", robots.lower())

    def test_build_dist_exports_store_assets_for_pages(self):
        written = build_dist(self.output_dir)

        self.assertIn(self.output_dir / "store" / "assets" / "store.min.js", written)
        self.assertIn(self.output_dir / "store" / "assets" / "store.home.min.css", written)
        self.assertIn(self.output_dir / "store" / "assets" / "store.collection.min.css", written)
        self.assertIn(self.output_dir / "store" / "assets" / "store.product.min.css", written)
        self.assertIn(self.output_dir / "store" / "assets" / "store.cart.min.css", written)
        self.assertIn(
            self.output_dir / "store" / "assets" / "fonts" / "SupremeLLWeb-Regular-store-latin.woff2",
            written,
        )

        headers = (self.output_dir / "_headers").read_text(encoding="utf-8")
        self.assertIn("/store/assets/*", headers)
        self.assertIn("Cache-Control: public, max-age=31536000, immutable", headers)
        self.assertIn("/robots.txt", headers)
        self.assertIn("Cache-Control: public, max-age=86400", headers)
        self.assertIn("/store/products/*", headers)
        self.assertNotIn("/*", headers.splitlines())

    def test_cloudflare_pages_pulse_function_is_declared(self):
        function_path = pocket.BASE_DIR / "functions" / "store" / "pulse.js"

        self.assertTrue(function_path.exists())
        source = function_path.read_text(encoding="utf-8")
        self.assertIn("export async function onRequestGet", source)
        self.assertIn("export async function onRequestPost", source)
        self.assertIn("receiver: \"cloudflare-pages-pulse\"", source)
        self.assertIn("status: 204", source)
        self.assertIn("Cache-Control", source)
