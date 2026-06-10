import shutil
import unittest

import app as pocket
from scripts.export_pages import build_dist


class PwaExportTest(unittest.TestCase):
    def setUp(self):
        self.output_dir = pocket.BASE_DIR / "tmp-test-dist-pwa"
        if self.output_dir.exists():
            shutil.rmtree(self.output_dir)

    def tearDown(self):
        if self.output_dir.exists():
            shutil.rmtree(self.output_dir)

    def test_build_dist_exports_minimal_pwa_shell(self):
        written = build_dist(self.output_dir)

        self.assertIn(self.output_dir / "pwa" / "index.html", written)
        self.assertIn(self.output_dir / "pwa" / "manifest.webmanifest", written)
        self.assertIn(self.output_dir / "pwa" / "service-worker.js", written)
        self.assertIn(self.output_dir / "pwa" / "app.js", written)
        self.assertIn(self.output_dir / "pwa" / "app.css", written)
        self.assertIn(self.output_dir / "pwa" / "catalog.json", written)
        self.assertIn(self.output_dir / "pwa" / "icons" / "icon-192.svg", written)
        self.assertIn(self.output_dir / "pwa" / "icons" / "icon-512.svg", written)
        self.assertNotIn(self.output_dir / "pwa" / "products", written)

        html = (self.output_dir / "pwa" / "index.html").read_text(encoding="utf-8")
        self.assertIn('rel="manifest"', html)
        self.assertIn('/pwa/service-worker.js', html)
        self.assertIn('data-pwa-root', html)

        manifest = (self.output_dir / "pwa" / "manifest.webmanifest").read_text(encoding="utf-8")
        self.assertIn('"display": "standalone"', manifest)
        self.assertIn('"start_url": "/pwa/"', manifest)
        self.assertIn('"icons"', manifest)

        service_worker = (self.output_dir / "pwa" / "service-worker.js").read_text(encoding="utf-8")
        self.assertIn("CACHE_NAME", service_worker)
        self.assertIn("/pwa/catalog.json", service_worker)
        self.assertIn("/store/catalog.json", service_worker)
        self.assertIn("offline", service_worker)

    def test_build_dist_exports_pwa_catalog_without_product_pages(self):
        written = build_dist(self.output_dir)

        self.assertIn(self.output_dir / "pwa" / "catalog.json", written)
        self.assertIn(self.output_dir / "pwa" / "cart-index.json", written)
        self.assertNotIn(self.output_dir / "pwa" / "products" / "the-cylinder-cord-necklace-cloud-blue" / "index.html", written)
        self.assertNotIn(self.output_dir / "pwa" / "collections" / "new-arrivals" / "index.html", written)

        catalog = (self.output_dir / "pwa" / "catalog.json").read_text(encoding="utf-8")
        self.assertIn('"products"', catalog)
