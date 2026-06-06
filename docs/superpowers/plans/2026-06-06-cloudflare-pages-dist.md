# Cloudflare Pages Dist Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Cloudflare Pages-ready `dist/` folder from the current Flask/Jinja storefront without duplicating template logic.

**Architecture:** Add a small Python exporter that imports `app.py`, uses Flask's test client to render known public routes, and writes static files into `dist/`. The exporter copies immutable static assets and writes a Cloudflare Pages `_headers` file so the deployed output keeps the cache behavior we designed for Lighthouse.

**Tech Stack:** Python, Flask test client, unittest, Cloudflare Pages static output.

---

### Task 1: Static Export Tests

**Files:**
- Create: `tests/test_static_export.py`

- [ ] **Step 1: Write the failing tests**

```python
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

        html = (self.output_dir / "store" / "index.html").read_text(encoding="utf-8")
        self.assertIn("Pocket Store", html)
        self.assertIn("/store/assets/store.home.min.css", html)
        self.assertIn("data-checkout-endpoint=\"/store/api/checkout\"", html)

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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m unittest discover -s tests -p 'test_static_export.py' -q`

Expected: FAIL with `ModuleNotFoundError: No module named 'scripts'` or `ImportError` because the exporter does not exist yet.

### Task 2: Exporter Implementation

**Files:**
- Create: `scripts/__init__.py`
- Create: `scripts/export_pages.py`
- Modify: `.gitignore`
- Test: `tests/test_static_export.py`

- [ ] **Step 1: Implement exporter**

Create `scripts/export_pages.py` with:
- `build_dist(output_dir=BASE_DIR / "dist")`
- static route rendering through `pocket.app.test_client()`
- product route generation from `pocket.store_products()`
- collection route generation from `pocket.store_collection_definitions()`
- fragment and JSON route generation
- asset export for minified JS, scoped CSS, fonts, and static pages
- `_headers` generation for Cloudflare Pages

- [ ] **Step 2: Ignore generated dist**

Add `dist/` and `tmp-test-dist/` to `.gitignore`.

- [ ] **Step 3: Run focused tests**

Run: `.venv/bin/python -m unittest discover -s tests -p 'test_static_export.py' -q`

Expected: PASS.

### Task 3: Verification and Commit

**Files:**
- Created/modified files from Tasks 1-2.

- [ ] **Step 1: Run full test suite**

Run: `.venv/bin/python -m unittest discover -s tests -q`

Expected: `Ran 210 tests` or more, `OK`.

- [ ] **Step 2: Build real dist**

Run: `.venv/bin/python scripts/export_pages.py`

Expected: `Built dist with ... files.`

- [ ] **Step 3: Inspect important output**

Run: `find dist -maxdepth 4 -type f | sort | sed -n '1,80p'`

Expected: includes root, BP, store pages, collection pages, product pages, assets, fonts, JSON, and `_headers`.

- [ ] **Step 4: Commit and push**

Run:

```bash
git add .gitignore docs/superpowers/plans/2026-06-06-cloudflare-pages-dist.md scripts tests/test_static_export.py
git commit -m "feat: add cloudflare pages static export"
git push origin master
```

Expected: commit and push complete.

### Task 4: Cloudflare Pages Setup

**Files:**
- No repo files unless Cloudflare requires a config file.

- [ ] **Step 1: Create Pages project from GitHub**

Use Cloudflare dashboard to create a Pages project connected to `ignasi-code/pocket-app`.

- [ ] **Step 2: Configure build**

Set:

```text
Build command: python3 -m pip install -r requirements.txt && python3 scripts/export_pages.py
Build output directory: dist
Root directory: /
Production branch: master
```

- [ ] **Step 3: Pause before sensitive steps**

Pause if Cloudflare asks for billing, DNS/custom domains, new GitHub OAuth permissions, or secret environment variables.
