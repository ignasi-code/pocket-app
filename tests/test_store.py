import html as html_lib
import unittest

import app as pocket


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.client = pocket.app.test_client()

    def store_css_source(self):
        path = pocket.BASE_DIR / "pages" / "store" / "store.css"
        if path.exists():
            return path.read_text(encoding="utf-8")
        return (pocket.BASE_DIR / "templates" / "store" / "base.html").read_text(encoding="utf-8")

    def store_js_source(self):
        return (pocket.BASE_DIR / "pages" / "store" / "store.js").read_text(encoding="utf-8")

    def first_available_variant(self):
        for product in pocket.load_store_catalog().get("products", []):
            for variant in product.get("variants", []):
                if variant.get("available") is not False:
                    return product, variant
        raise AssertionError("Test catalog needs at least one available variant.")

    def test_store_page_is_public(self):
        response = self.client.get("/store")
        self.addCleanup(response.close)

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("Pocket Store", html)
        self.assertIn("data-quickshop-open", html)
        self.assertIn("/store/cart", html)

    def assert_edge_cache_headers(self, response, browser_max_age, edge_max_age):
        cache_control = response.headers.get("Cache-Control", "")
        cdn_cache_control = response.headers.get("CDN-Cache-Control", "")
        cloudflare_cache_control = response.headers.get("Cloudflare-CDN-Cache-Control", "")

        self.assertIn("public", cache_control)
        self.assertIn(f"max-age={browser_max_age}", cache_control)
        self.assertIn(f"max-age={edge_max_age}", cdn_cache_control)
        self.assertIn("stale-while-revalidate", cdn_cache_control)
        self.assertEqual(cdn_cache_control, cloudflare_cache_control)

    def test_store_browsing_routes_are_explicitly_edge_cacheable(self):
        cases = (
            "/store",
            "/store/collections/new-arrivals",
            "/store/products/the-cylinder-cord-necklace-cloud-blue",
            "/store/cart",
        )

        for path in cases:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.addCleanup(response.close)

                self.assertEqual(response.status_code, 200)
                self.assert_edge_cache_headers(response, browser_max_age=300, edge_max_age=86400)

    def test_store_data_and_assets_expose_edge_cache_headers(self):
        cases = (
            ("/store/catalog.json", 3600, 86400),
            ("/store/cart-index.json", 3600, 86400),
            ("/store/assets/store.min.js?v=20260605-js-min", 31536000, 31536000),
            ("/store/assets/store.home.min.css?v=20260605-scope-css-menu-drawer", 31536000, 31536000),
            ("/store/assets/fonts/SupremeLLWeb-Regular-store-latin.woff2", 31536000, 31536000),
        )

        for path, browser_max_age, edge_max_age in cases:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.addCleanup(response.close)

                self.assertEqual(response.status_code, 200)
                self.assert_edge_cache_headers(response, browser_max_age, edge_max_age)

    def test_store_checkout_api_is_never_cacheable(self):
        _product, variant = self.first_available_variant()
        response = self.client.post(
            "/store/api/checkout",
            json={"cartItems": [{"id": int(variant["id"]), "qty": 1}]},
        )
        self.addCleanup(response.close)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("Cache-Control"), "no-store")
        self.assertNotIn("CDN-Cache-Control", response.headers)

    def test_store_base_declares_inline_favicon_to_avoid_browser_404(self):
        response = self.client.get("/store")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('<link rel="icon" href="data:,">', html)

    def test_homepage_uses_live_theme_module_structure(self):
        response = self.client.get("/store")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("product-module__description", html)
        self.assertIn("product-module__title", html)
        self.assertIn("product-module__products", html)
        self.assertIn("product-module__cta product-module__cta--desktop", html)
        self.assertIn("product-module__cta product-module__cta--mobile", html)
        self.assertIn("double-image-banner", html)
        self.assertIn("double-image-banner__tile__image", html)
        self.assertIn("double-image-banner__tile__cta", html)
        self.assertIn("category-module__text", html)
        self.assertIn("category-module__text--pink", html)
        self.assertIn("info-module__content mobile-visible", html)
        self.assertIn("info-module__content desktop-visible", html)

    def test_store_base_loads_css_without_render_blocking_lighthouse(self):
        response = self.client.get("/store")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('<style data-critical-store-css>', html)
        self.assertIn(".site-header", html)
        self.assertIn(".hero__image", html)
        self.assertIn('<link rel="preload" href="/store/assets/store.home.min.css?v=20260605-scope-css-menu-drawer" as="style" fetchpriority="low" onload="this.onload=null;this.rel=&#39;stylesheet&#39;">', html)
        self.assertIn('<noscript><link rel="stylesheet" href="/store/assets/store.home.min.css?v=20260605-scope-css-menu-drawer"></noscript>', html)
        self.assertNotIn("20260605-scope-css-cart-cls", html)
        self.assertNotIn('<link rel="stylesheet" href="/store/assets/store.css', html)

    def test_product_page_inlines_pdp_above_fold_critical_css_for_lighthouse(self):
        product_response = self.client.get("/store/products/the-cylinder-cord-necklace-cloud-blue")
        home_response = self.client.get("/store")

        self.assertEqual(product_response.status_code, 200)
        self.assertEqual(home_response.status_code, 200)
        product_html = product_response.get_data(as_text=True)
        home_html = home_response.get_data(as_text=True)
        critical_start = product_html.index('<style data-critical-store-css>')
        critical_end = product_html.index("</style>", critical_start)
        product_critical_css = product_html[critical_start:critical_end]

        self.assertIn(".product-page{padding-top:5px", product_critical_css)
        self.assertIn(".pdp,.product-info{display:block", product_critical_css)
        self.assertIn(".product-gallery__image__wrapper{border:1px solid #e6e6e6", product_critical_css)
        self.assertIn("flex:0 0 calc(100vw - 8px)", product_critical_css)
        self.assertIn(".product-details-top{padding:0 30px 44px", product_critical_css)
        self.assertIn(".product-details-bottom__col--options{border-bottom:1px solid #e6e6e6;order:1", product_critical_css)
        self.assertNotIn(".product-gallery__image__wrapper{border:1px solid #e6e6e6", home_html)

    def test_collection_page_inlines_hero_critical_css_for_lighthouse(self):
        collection_response = self.client.get("/store/collections/new-arrivals")
        home_response = self.client.get("/store")

        self.assertEqual(collection_response.status_code, 200)
        self.assertEqual(home_response.status_code, 200)
        collection_html = collection_response.get_data(as_text=True)
        home_html = home_response.get_data(as_text=True)
        critical_start = collection_html.index('<style data-critical-store-css>')
        critical_end = collection_html.index("</style>", critical_start)
        collection_critical_css = collection_html[critical_start:critical_end]

        self.assertIn(".collection,.collection-page{box-sizing:border-box", collection_critical_css)
        self.assertIn(".collection-hero__image{border-radius:6px", collection_critical_css)
        self.assertIn(".collection-hero__image::before{content:\"\";display:block;padding-top:102%", collection_critical_css)
        self.assertIn(".collection-filter-bar{background:#fff;display:grid", collection_critical_css)
        self.assertNotIn(".collection-hero__image{border-radius:6px", home_html)

    def test_cart_page_inlines_summary_critical_css_for_lighthouse(self):
        cart_response = self.client.get("/store/cart")
        home_response = self.client.get("/store")

        self.assertEqual(cart_response.status_code, 200)
        self.assertEqual(home_response.status_code, 200)
        cart_html = cart_response.get_data(as_text=True)
        home_html = home_response.get_data(as_text=True)
        critical_start = cart_html.index('<style data-critical-store-css>')
        critical_end = cart_html.index("</style>", critical_start)
        cart_critical_css = cart_html[critical_start:critical_end]

        self.assertIn(".cart{padding:79px 0 0", cart_critical_css)
        self.assertIn(".cart-page{display:block;padding:0 10px", cart_critical_css)
        self.assertIn(".cart-page__summary{background:#fff;border:1px solid #e6e6e6", cart_critical_css)
        self.assertIn(".cart-page__checkout{align-items:center;appearance:none;background:#d1ebf8", cart_critical_css)
        self.assertIn(".cart-page__items{background:transparent;border:0", cart_critical_css)
        self.assertNotIn(".cart-page__summary{background:#fff;border:1px solid #e6e6e6", home_html)

    def test_mobile_header_uses_lighthouse_safe_tap_targets(self):
        response = self.client.get("/store")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        source = self.store_css_source()
        self.assertIn(".brand{align-items:center;background:#fff;border:1px solid rgba(0,0,0,.1);border-radius:5px;box-sizing:border-box;display:flex;height:59px;justify-content:center;left:58px;margin:0;position:absolute;right:95px;top:0}", html)
        self.assertIn(".store-search{background:#fff;border:1px solid rgba(0,0,0,.1);border-radius:5px;box-sizing:border-box;cursor:pointer;height:59px;padding:0;position:absolute;right:48px;top:0;width:48px;z-index:2}", html)
        self.assertIn(".cart-link{appearance:none;background:#b9d2e8;border:1px solid rgba(0,0,0,.1);border-radius:5px;box-sizing:border-box;color:#000;cursor:pointer;display:flex;font-size:.75rem;font-weight:700;height:59px;justify-content:center;line-height:59px;min-height:0;padding:0;position:absolute;right:0;text-align:center;top:0;width:48px;z-index:2}", html)
        self.assertIn("right: 95px;", source)
        self.assertIn("right: 48px;", source)
        self.assertIn("width: 48px;", source)

    def test_store_pages_include_lighthouse_accessibility_landmarks_and_headings(self):
        home_html = self.client.get("/store").get_data(as_text=True)
        cart_html = self.client.get("/store/cart").get_data(as_text=True)
        collection_html = self.client.get("/store/collections/new-arrivals").get_data(as_text=True)

        self.assertIn('<h1 class="visually-hidden">Roxanne Assoulin storefront</h1>', home_html)
        self.assertIn('<h1 class="visually-hidden">Shopping bag</h1>', cart_html)
        self.assertIn('class="shipping-promo js-shippingPromo" role="region" aria-label="Shipping promotion"', home_html)
        self.assertIn('class="shipping-promo js-shippingPromo" role="region" aria-label="Shipping promotion"', collection_html)
        self.assertIn('<h2 class="visually-hidden">Products</h2>', collection_html)

    def test_store_accessibility_fixes_avoid_axe_violations(self):
        product_html = self.client.get("/store/products/the-cylinder-cord-necklace-cloud-blue").get_data(as_text=True)
        cart_html = self.client.get("/store/cart").get_data(as_text=True)
        css = self.store_css_source()
        js = self.store_js_source()

        self.assertIn(".price {\n      color: #000;\n      font-size: .75rem;\n      font-weight: 400;\n      line-height: 1.35;\n      opacity: .65;", css)
        self.assertIn(".product-tile__price {\n      color: #000;\n      font-size: .75rem;\n      font-weight: 400;\n      line-height: 135%;\n      opacity: .65;", css)
        self.assertIn('<div class="buy-box product-details">', product_html)
        self.assertNotIn('<aside class="buy-box product-details">', product_html)
        self.assertIn('aria-label="Quantity"', product_html)
        self.assertIn('<div class="cart-page__summary cart-page__totals">', cart_html)
        self.assertNotIn('<aside class="cart-page__summary cart-page__totals">', cart_html)
        self.assertIn('aria-label="${escapeHtml(meta.product.title)}"', js)
        self.assertIn('data-gift-save', js)
        self.assertIn('saveButton.disabled = !active;', js)

    def test_store_pages_use_route_scoped_css_assets_for_lighthouse(self):
        cases = (
            ("/store", "home"),
            ("/store/collections/new-arrivals", "collection"),
            ("/store/products/the-cylinder-cord-necklace-cloud-blue", "product"),
            ("/store/cart", "cart"),
        )

        for path, scope in cases:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                html = response.get_data(as_text=True)
                href = f"/store/assets/store.{scope}.min.css?v=20260605-scope-css-menu-drawer"
                self.assertIn(href, html)
                self.assertNotIn("/store/assets/store.min.css?v=20260605-cart-cls", html)

    def test_store_critical_css_keeps_hidden_drawers_out_of_first_paint_flow(self):
        response = self.client.get("/store")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn(".search-drawer,.cart-notification,.cart-notification__overlay,.promo,.quickshop__overlay,.quickshop__drawer,.menu-drawer,.cart-drawer", html)
        self.assertIn("position:fixed;top:0;visibility:hidden;width:0", html)

    def test_store_critical_css_hides_accessibility_text_before_scoped_css_loads(self):
        response = self.client.get("/store")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        critical_start = html.index('<style data-critical-store-css>')
        critical_end = html.index("</style>", critical_start)
        critical_css = html[critical_start:critical_end]

        self.assertIn(".visually-hidden{border:0;clip:rect(0 0 0 0);height:1px", critical_css)
        self.assertIn('<h1 class="visually-hidden">Roxanne Assoulin storefront</h1>', html)

    def test_store_critical_css_stabilizes_above_fold_controls_before_scoped_css_loads(self):
        response = self.client.get("/store")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        critical_start = html.index('<style data-critical-store-css>')
        critical_end = html.index("</style>", critical_start)
        critical_css = html[critical_start:critical_end]

        self.assertIn(".hero__cta:before,.hero__cta:after{box-sizing:border-box;content:\"\";position:absolute", critical_css)
        self.assertIn(".shipping-promo__close{background:transparent;border:0;cursor:pointer;height:50px", critical_css)
        self.assertIn(".shipping-promo__close:before,.shipping-promo__close:after{background:#fff;content:\"\";height:1px", critical_css)

    def test_store_css_asset_is_cacheable_for_lighthouse(self):
        response = self.client.get("/store/assets/store.css?v=20260605-css-images")
        self.addCleanup(response.close)

        self.assertEqual(response.status_code, 200)
        self.assertIn("public", response.headers.get("Cache-Control", ""))
        self.assertIn("max-age=31536000", response.headers.get("Cache-Control", ""))
        self.assertIn(".site-header", response.get_data(as_text=True))

    def test_store_minified_css_asset_is_cacheable_for_lighthouse(self):
        response = self.client.get("/store/assets/store.min.css?v=20260605-cart-cls")
        self.addCleanup(response.close)

        self.assertEqual(response.status_code, 200)
        text = response.get_data(as_text=True)
        self.assertIn("public", response.headers.get("Cache-Control", ""))
        self.assertIn("max-age=31536000", response.headers.get("Cache-Control", ""))
        self.assertIn(".site-header", text)
        self.assertLess(len(text), len(self.store_css_source()))
        self.assertLess(len(text), 51000)
        self.assertNotIn("ui-sans-serif", text)
        self.assertNotIn("border-radius:999px", text)
        self.assertNotIn("Roxanne Assoulin fidelity pass", text)

    def test_store_scoped_css_assets_are_cacheable_and_smaller_for_lighthouse(self):
        full_response = self.client.get("/store/assets/store.min.css?v=20260605-cart-cls")
        self.addCleanup(full_response.close)
        full_length = len(full_response.get_data(as_text=True))
        cases = {
            "home": (".product-module", ".collection-hero", ".product-details", ".cart-page"),
            "collection": (".collection-hero", ".product-module", ".product-details", ".cart-page"),
            "product": (".product-details", ".collection-hero", ".product-module", ".cart-page"),
            "cart": (".cart-page", ".collection-hero", ".product-details", ".product-module"),
        }

        for scope, markers in cases.items():
            with self.subTest(scope=scope):
                response = self.client.get(f"/store/assets/store.{scope}.min.css?v=20260605-scope-css-cart-cls")
                self.addCleanup(response.close)
                text = response.get_data(as_text=True)
                present, *absent = markers

                self.assertEqual(response.status_code, 200)
                self.assertIn("public", response.headers.get("Cache-Control", ""))
                self.assertIn("max-age=31536000", response.headers.get("Cache-Control", ""))
                self.assertIn("/store/assets/fonts/SupremeLLWeb-Regular-store-latin.woff2", text)
                self.assertIn(".site-header", text)
                self.assertIn(".footer", text)
                self.assertIn(".cart-drawer", text)
                self.assertIn(present, text)
                for marker in absent:
                    self.assertNotIn(marker, text)
                self.assertLess(len(text), full_length)
                self.assertLess(len(text), 33000)

    def test_store_defers_relative_mono_font_until_user_motion(self):
        css_response = self.client.get("/store/assets/store.min.css?v=20260605-cart-cls")
        self.addCleanup(css_response.close)
        script_response = self.client.get("/store/assets/store.min.js?v=20260605-js-min")
        self.addCleanup(script_response.close)

        self.assertEqual(css_response.status_code, 200)
        self.assertEqual(script_response.status_code, 200)
        css = css_response.get_data(as_text=True)
        script = script_response.get_data(as_text=True)
        self.assertNotIn("relative-mono-10-pitch-pro.woff2", css)
        self.assertIn("font-family:RelativeMono", css)
        self.assertIn("function loadDeferredMonoFont()", script)
        self.assertIn("relative-mono-10-pitch-pro.woff2", script)
        self.assertIn('window.addEventListener("scroll", loadDeferredMonoFont', script)

    def test_store_uses_cacheable_local_subset_supreme_fonts(self):
        response = self.client.get("/store/assets/store.min.css?v=20260605-cart-cls")
        self.addCleanup(response.close)

        self.assertEqual(response.status_code, 200)
        css = response.get_data(as_text=True)
        self.assertIn('/store/assets/fonts/SupremeLLWeb-Regular-store-latin.woff2', css)
        self.assertIn('/store/assets/fonts/SupremeLLWeb-Medium-store-latin.woff2', css)
        self.assertNotIn('/store/assets/fonts/SupremeLLWeb-Regular-store-tight.woff2', css)
        self.assertNotIn('/store/assets/fonts/SupremeLLWeb-Medium-store-tight.woff2', css)
        self.assertNotIn("https://roxanneassoulin.com/cdn/shop/t/147/assets/SupremeLLWeb-Regular.woff2", css)
        self.assertNotIn("https://roxanneassoulin.com/cdn/shop/t/147/assets/SupremeLLWeb-Medium.woff2", css)

        for filename in (
            "SupremeLLWeb-Regular-store-latin.woff2",
            "SupremeLLWeb-Medium-store-latin.woff2",
        ):
            with self.subTest(filename=filename):
                font_response = self.client.get(f"/store/assets/fonts/{filename}")
                self.addCleanup(font_response.close)

                self.assertEqual(font_response.status_code, 200)
                self.assertIn("public", font_response.headers.get("Cache-Control", ""))
                self.assertIn("max-age=31536000", font_response.headers.get("Cache-Control", ""))
                self.assertEqual(font_response.mimetype, "font/woff2")
                self.assertLess(len(font_response.data), 10000)

    def test_store_base_has_meta_description_for_seo_score(self):
        response = self.client.get("/store")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('<meta name="description" content="A static-first Roxanne Assoulin storefront prototype with fast collection, product, and cart views.">', html)

    def test_store_templates_trim_jinja_whitespace_for_payload_size(self):
        self.assertTrue(pocket.app.jinja_env.trim_blocks)
        self.assertTrue(pocket.app.jinja_env.lstrip_blocks)

    def test_store_pages_minify_intertag_whitespace_for_payload_size(self):
        response = self.client.get("/store")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertNotRegex(html, r">\s+<")
        self.assertLess(len(html.encode()), 45000)

    def test_store_preconnects_remote_image_origins(self):
        response = self.client.get("/store")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('<link rel="preconnect" href="https://cdn.shopify.com">', html)
        self.assertIn('<link rel="preconnect" href="https://roxanneassoulin.com">', html)
        self.assertNotIn('href="https://roxanneassoulin.com" crossorigin', html)

    def test_store_logo_images_have_explicit_dimensions(self):
        response = self.client.get("/store")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('alt="Roxanne Assoulin" width="580" height="42"', html)
        self.assertIn("roxane-assoulin-logo.png?v=157219181899558921191761553533&amp;quality=60&amp;width=207\" srcset=", html)
        self.assertNotIn("roxane-assoulin-logo.png?v=157219181899558921191761553533&amp;quality=60&amp;width=414\" srcset=", html)
        self.assertIn("roxane-assoulin-logo.png?v=157219181899558921191761553533&amp;quality=60&amp;width=207 207w", html)
        self.assertIn("roxane-assoulin-logo.png?v=157219181899558921191761553533&amp;quality=60&amp;width=414 414w", html)
        self.assertIn('sizes="(min-width: 1024px) 290px, 207px"', html)
        self.assertIn('loading="lazy" decoding="async"', html)
        source = self.store_css_source()
        self.assertIn(".brand img {\n      display: block;\n      height: auto;\n      width: 207px;", source)
        self.assertIn(".footer__logo img {\n      height: auto;\n      width: 103px;", source)

    def test_shopify_image_urls_strip_legacy_size_before_width_transform(self):
        url = pocket.store_image_url(
            "https://roxanneassoulin.com/cdn/shop/files/0531_MainImage_Mobile_079fd26c-9edc-4895-b83a-8fbaec281985_760x_crop_center.jpg?v=1780086212",
            width=390,
        )

        self.assertIn("0531_MainImage_Mobile_079fd26c-9edc-4895-b83a-8fbaec281985.jpg", url)
        self.assertIn("quality=60", url)
        self.assertIn("width=390", url)
        self.assertLess(url.index("quality=60"), url.index("width=390"))
        self.assertNotIn("_760x_crop_center", url)

    def test_store_frontend_shopify_image_helper_adds_quality_transform(self):
        source = self.store_js_source()
        helper_source = source[
            source.index("function shopifyImageUrl(src, width)"):
            source.index("function productImage(product, variant, width)")
        ]

        self.assertIn('url.searchParams.delete("quality");', helper_source)
        self.assertIn('if (width) url.searchParams.set("quality", "60");', helper_source)
        self.assertLess(
            helper_source.index('url.searchParams.set("quality", "60")'),
            helper_source.index('url.searchParams.set("width", String(width))'),
        )

    def test_homepage_preloads_lcp_hero_responsive_image_for_lighthouse(self):
        response = self.client.get("/store")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        preload_start = html.index('<link rel="preload" as="image" media="(max-width: 1023px)"')
        preload_end = html.index(">", preload_start)
        preload_tag = html[preload_start:preload_end]
        self.assertIn('imagesrcset="https://roxanneassoulin.com/cdn/shop/files/0531_MainImage_Mobile_079fd26c-9edc-4895-b83a-8fbaec281985.jpg?v=1780086212&amp;quality=60&amp;width=390 390w', preload_tag)
        self.assertNotIn("&amp;width=414", preload_tag)
        self.assertNotIn("&amp;width=420", preload_tag)
        self.assertNotIn("&amp;width=480 480w", preload_tag)
        self.assertNotIn("&amp;width=640 640w", html)
        self.assertIn('imagesizes="100vw"', html)
        self.assertIn('fetchpriority="high"', html)

    def test_collection_preloads_mobile_lcp_hero_for_lighthouse(self):
        response = self.client.get("/store/collections/new-arrivals")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        preload_start = html.index('<link rel="preload" as="image" media="(max-width: 1023px)"')
        preload_end = html.index(">", preload_start)
        preload_tag = html[preload_start:preload_end]
        self.assertIn("New-Arrivals.jpg", html)
        self.assertIn("&amp;width=390 390w", preload_tag)
        self.assertNotIn("&amp;width=414", preload_tag)
        self.assertNotIn("&amp;width=420", preload_tag)
        self.assertNotIn("&amp;width=480 480w", preload_tag)
        self.assertIn('imagesizes="100vw"', html)
        self.assertIn('fetchpriority="high"', html)
        self.assertIn('src="https://roxanneassoulin.com/cdn/shop/collections/New-Arrivals.jpg?v=1779127477&amp;quality=60&amp;width=390"', html)

    def test_product_page_preloads_mobile_lcp_gallery_image_for_lighthouse(self):
        response = self.client.get("/store/products/the-cylinder-cord-necklace-cloud-blue")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        preload_start = html.index('<link rel="preload" as="image" media="(max-width: 1023px)"')
        preload_end = html.index(">", preload_start)
        preload_tag = html[preload_start:preload_end]
        self.assertIn("THE_CYLINDER_CORD_NECKLACE_2495", html)
        self.assertIn("&amp;width=390 390w", preload_tag)
        self.assertNotIn("&amp;width=414", preload_tag)
        self.assertNotIn("&amp;width=420", preload_tag)
        self.assertNotIn("&amp;width=480 480w", preload_tag)
        self.assertIn('imagesizes="100vw"', html)
        self.assertIn('fetchpriority="high"', html)
        first_img_start = html.index('<img src="https://cdn.shopify.com/s/files/1/0998/6780/files/THE_CYLINDER_CORD_NECKLACE_2495.jpg?v=')
        first_img_end = html.index(">", first_img_start)
        self.assertIn("&amp;width=390", html[first_img_start:first_img_end])
        self.assertNotIn("&amp;width=414", html[first_img_start:first_img_end])
        self.assertNotIn("&amp;width=420", html[first_img_start:first_img_end])
        self.assertNotIn("&amp;width=760", html[first_img_start:first_img_end])
        self.assertNotIn("&amp;width=1200", html[first_img_start:first_img_end])

    def test_product_page_defers_non_lcp_gallery_images_for_mobile_lighthouse(self):
        response = self.client.get("/store/products/the-cylinder-cord-necklace-cloud-blue")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        second_img_start = html.index('<img data-gallery-deferred data-src="https://cdn.shopify.com/s/files/1/0998/6780/files/CYLINDER_DUNE_NECKLACE_2633.jpg?v=')
        second_img_end = html.index(">", second_img_start)
        second_img_tag = html[second_img_start:second_img_end]
        self.assertIn("data-src=", second_img_tag)
        self.assertIn("data-srcset=", second_img_tag)
        self.assertIn("data-sizes=", second_img_tag)
        self.assertIn("&amp;width=420", second_img_tag)
        self.assertNotIn("&amp;width=480", second_img_tag)
        self.assertIn('loading="lazy"', second_img_tag)
        self.assertNotIn(" src=", second_img_tag)
        self.assertNotIn(" srcset=", second_img_tag)

    def test_product_page_defers_below_fold_detail_image_for_mobile_lighthouse(self):
        response = self.client.get("/store/products/the-cylinder-cord-necklace-cloud-blue")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        image_marker = "data-product-details-deferred-image"
        image_marker_start = html.index(image_marker)
        image_start = html.rindex("<img", 0, image_marker_start)
        image_end = html.index(">", image_marker_start)
        image_tag = html[image_start:image_end]

        self.assertIn("data-src=", image_tag)
        self.assertIn("data-srcset=", image_tag)
        self.assertIn("data-sizes=", image_tag)
        self.assertIn('loading="lazy"', image_tag)
        self.assertNotIn(" src=", image_tag)
        self.assertNotIn(" srcset=", image_tag)

    def test_product_deferred_detail_image_hides_broken_placeholder_before_hydration(self):
        source = self.store_css_source()

        self.assertIn(".product-details-top__image img[data-product-details-deferred-image]:not([src])", source)
        self.assertIn("visibility: hidden", source)

    def test_product_gallery_deferred_images_hydrate_after_user_motion(self):
        source = (pocket.BASE_DIR / "pages" / "store" / "store.js").read_text(encoding="utf-8")
        gallery_source = source[
            source.index("function hydrateVisibleGalleryImages"):
            source.index("function escapeHtml")
        ]

        self.assertIn("hydrateDeferredImage", source)
        self.assertIn("bindDeferredGalleryHydration", source)
        self.assertIn("hydrateVisibleGalleryImages", source)
        self.assertIn("[data-gallery-image][data-src]", source)
        self.assertIn("hydrateDeferredImage(image);", source)
        self.assertIn('gallery.addEventListener("scroll"', source)
        self.assertIn('gallery.addEventListener("pointerdown"', source)
        self.assertNotIn("new IntersectionObserver", gallery_source)
        self.assertNotIn("observeDeferredGalleryImages();", gallery_source)

    def test_product_detail_image_hydrates_after_user_motion(self):
        source = (pocket.BASE_DIR / "pages" / "store" / "store.js").read_text(encoding="utf-8")

        self.assertIn("function hydrateVisibleProductDetailImages()", source)
        self.assertIn("function bindDeferredProductDetailImageHydration()", source)
        self.assertIn("[data-product-details-deferred-image][data-src]", source)
        self.assertIn('window.addEventListener("scroll"', source)
        self.assertIn('window.addEventListener("pointerdown"', source)
        self.assertIn("bindDeferredProductDetailImageHydration();", source)

    def test_homepage_mobile_shipping_grid_includes_heart_tile(self):
        response = self.client.get("/store")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("info-module__span--heart mobile-heart", html)

    def test_home_and_collection_render_live_shipping_promo_bar(self):
        for path in ("/store", "/store/collections/new-arrivals"):
            with self.subTest(path=path):
                response = self.client.get(path)

                self.assertEqual(response.status_code, 200)
                html = response.get_data(as_text=True)
                self.assertIn('class="shipping-promo js-shippingPromo"', html)
                self.assertIn("Enjoy complimentary ground shipping on US orders $250+", html)
                self.assertIn("data-shipping-promo-close", html)

    def test_shipping_promo_installs_no_flash_persistence_gate(self):
        response = self.client.get("/store")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('<script data-shipping-promo-gate>', html)
        self.assertIn('pocket_store_shipping_promo_dismissed', html)
        self.assertIn('document.documentElement.classList.add("shipping-promo-dismissed")', html)
        self.assertIn(".shipping-promo-dismissed .shipping-promo", html)

    def test_store_javascript_persists_shipping_promo_dismissal(self):
        source = (pocket.BASE_DIR / "pages" / "store" / "store.js").read_text(encoding="utf-8")

        self.assertIn('const SHIPPING_PROMO_DISMISSED_KEY = "pocket_store_shipping_promo_dismissed";', source)
        self.assertIn('localStorage.setItem(SHIPPING_PROMO_DISMISSED_KEY, "1");', source)
        self.assertIn('document.documentElement.classList.add("shipping-promo-dismissed");', source)
        self.assertIn("hideDismissedShippingPromos();", source)

    def test_product_page_renders_live_shipping_promo_like_original(self):
        response = self.client.get("/store/products/the-cylinder-cord-necklace-cloud-blue")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('class="shipping-promo js-shippingPromo" role="region" aria-label="Shipping promotion"', html)
        self.assertIn("Enjoy complimentary ground shipping on US orders $250+", html)
        self.assertIn("data-shipping-promo-close", html)

    def test_shipping_promo_css_matches_live_mobile_bar(self):
        source = self.store_css_source()

        self.assertIn(".shipping-promo {\n      background: #cf3d2f;", source)
        self.assertIn("position: fixed;\n      right: 10px;\n      top: 79px;", source)
        self.assertIn(".shipping-promo span {\n      display: block;\n      min-width: 0;", source)
        self.assertIn(".shipping-promo.is-hidden {\n      display: none;", source)

    def test_shipping_promo_css_matches_live_desktop_compact_box(self):
        source = self.store_css_source()

        self.assertIn(".shipping-promo {\n        background: #c5402c;\n        display: block;\n        height: 81px;\n        left: auto;", source)
        self.assertIn("padding: 20px 60px 20px 19px;\n        right: 10px;\n        top: 79px;\n        width: 320px;", source)
        self.assertIn(".shipping-promo__close {\n        height: 48px;\n        margin-top: 16px;\n        right: 8px;\n        top: 0;\n        width: 48px;", source)

    def test_homepage_product_module_title_uses_live_regular_weight(self):
        source = self.store_css_source()

        self.assertIn(".product-module__title", source)
        self.assertIn("font-weight: 400", source)

    def test_homepage_desktop_category_module_matches_live_height(self):
        source = self.store_css_source()

        self.assertIn(".category-module {\n        height: 460px;\n        padding: 0;", source)
        self.assertIn(".category-module__text {\n        font-size: 3rem;\n        line-height: 1.2;", source)
        self.assertIn("max-width: 850px;\n        padding-bottom: 177px;", source)
        self.assertIn(".category-module__text--pink::after {\n        border-bottom: 2px solid #000;\n        top: 57px;", source)

    def test_homepage_split_banner_uses_live_mobile_cta_treatment(self):
        source = self.store_css_source()

        self.assertIn(".double-image-banner__tile a", source)
        self.assertIn("bottom: 5%", source)
        self.assertIn("font-size: 1rem", source)
        self.assertIn("left: 50%", source)
        self.assertIn("transform: translate3d(-57%, -50%, 0)", source)
        self.assertIn(".double-image-banner__tile__cta--black", source)
        self.assertNotIn(".split-tile::before", source)
        self.assertNotIn("font-size: 9.375rem", source)

    def test_homepage_desktop_product_module_matches_live_spacing(self):
        source = self.store_css_source()

        self.assertIn(".product-module__title {\n        font-size: 3rem;\n        line-height: 1.2;", source)
        self.assertIn("padding-bottom: 30px;\n        padding-left: 65px;", source)
        self.assertIn(".product-module__cta {\n        font-size: 1.125rem;\n        padding-right: 92px;", source)
        self.assertIn(".product-module__products {\n        flex-wrap: wrap;\n        padding: 0 2px 1px;", source)

    def test_homepage_desktop_product_module_matches_live_height_contract(self):
        source = self.store_css_source()

        self.assertIn(".product-module {\n        padding: 40px 0 50px;", source)
        self.assertIn("max-width: 559px;\n        padding-bottom: 30px;", source)
        self.assertIn(".product-module__cta--desktop {\n        display: block;", source)
        self.assertIn(".product-module__cta--mobile {\n        display: none;", source)

    def test_homepage_desktop_hero_matches_live_viewport_contract(self):
        source = self.store_css_source()

        self.assertIn(".hero {\n        padding: 2px;", source)
        self.assertIn(".hero__image,\n      .hero img {\n        height: calc(100vh - 4px);", source)

    def test_store_skips_below_fold_render_work_for_lighthouse(self):
        source = self.store_css_source()

        self.assertIn(".home > .shopify-section:nth-child(n+2),", source)
        self.assertIn(".collection-grid .product-tile:nth-child(n+5),", source)
        self.assertIn(".footer {\n      content-visibility: auto;", source)
        self.assertIn("contain-intrinsic-size: auto 900px;", source)

    def test_homepage_marks_first_hero_as_lcp_image(self):
        response = self.client.get("/store")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('fetchpriority="high"', html)
        self.assertIn('loading="eager"', html)
        self.assertIn('decoding="async"', html)
        self.assertIn('width="760"', html)
        self.assertIn('height="760"', html)

    def test_homepage_hero_uses_responsive_shopify_image_delivery(self):
        response = self.client.get("/store")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("MainImage_Mobile", html)
        first_img_start = html.index('<img src="https://roxanneassoulin.com/cdn/shop/files/0531_MainImage_Mobile')
        first_img_end = html.index(">", first_img_start)
        first_img_tag = html[first_img_start:first_img_end]
        self.assertIn("&amp;width=390\"", first_img_tag)
        self.assertIn("&amp;width=390 390w", first_img_tag)
        self.assertNotIn("&amp;width=414", first_img_tag)
        self.assertNotIn("&amp;width=420", first_img_tag)
        self.assertNotIn("&amp;width=480 480w", first_img_tag)
        self.assertNotIn("&amp;width=560 560w", html)
        self.assertNotIn("&amp;width=640 640w", html)
        self.assertNotIn("_760x_crop_center.jpg?v=1780086212&amp;width", html)
        self.assertIn('sizes="100vw"', html)

    def test_homepage_hero_cta_uses_contrast_safe_text_color(self):
        response = self.client.get("/store")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn(".hero__cta{bottom:40px;color:#000;", html)
        source = self.store_css_source()
        self.assertIn(".hero__cta {\n      bottom: 40px;\n      color: #000;", source)

    def test_homepage_image_only_split_banner_links_have_accessible_labels(self):
        response = self.client.get("/store")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('aria-label="Shop The Happy Baby Necklace"', html)
        self.assertIn('aria-label="Shop The Cord Charms"', html)
        self.assertIn('aria-label="Schedule an appointment"', html)

    def test_product_tiles_use_responsive_shopify_image_delivery(self):
        response = self.client.get("/store")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('class="product-tile__image__primary"', html)
        self.assertIn("&amp;width=360 360w", html)
        self.assertIn("&amp;width=540 540w", html)
        self.assertIn('sizes="(min-width: 1024px) 25vw, 50vw"', html)

    def test_homepage_product_module_defers_card_primary_images_for_lighthouse(self):
        response = self.client.get("/store")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        module_start = html.index('<section class="shopify-section product-module">')
        image_start = html.index('<img class="product-tile__image__primary"', module_start)
        image_end = html.index(">", image_start)
        image_tag = html[image_start:image_end]

        self.assertIn("data-product-card-deferred-image", image_tag)
        self.assertIn("data-src=", image_tag)
        self.assertIn("data-srcset=", image_tag)
        self.assertIn("data-sizes=", image_tag)
        self.assertNotIn(" src=", image_tag)
        self.assertNotIn(" srcset=", image_tag)

    def test_collection_loads_first_visible_product_row_then_defers_rest(self):
        response = self.client.get("/store/collections/new-arrivals")
        fragment_response = self.client.get("/store/collections/new-arrivals/products-fragment?offset=12")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(fragment_response.status_code, 200)
        html = response.get_data(as_text=True)
        fragment_html = fragment_response.get_data(as_text=True)
        grid_start = html.index('<section class="grid collection-grid" data-collection-grid>')
        first_start = html.index('<img class="product-tile__image__primary"', grid_start)
        first_end = html.index(">", first_start)
        first_tag = html[first_start:first_end]
        second_start = html.index('<img class="product-tile__image__primary"', first_end)
        second_end = html.index(">", second_start)
        second_tag = html[second_start:second_end]
        third_start = html.index('<img class="product-tile__image__primary"', second_end)
        third_end = html.index(">", third_start)
        third_tag = html[third_start:third_end]

        self.assertIn('src="https://', first_tag)
        self.assertIn("srcset=", first_tag)
        self.assertNotIn("data-product-card-deferred-image", first_tag)
        self.assertNotIn("data-src=", first_tag)
        self.assertIn('src="https://', second_tag)
        self.assertIn("srcset=", second_tag)
        self.assertNotIn("data-product-card-deferred-image", second_tag)
        self.assertNotIn("data-src=", second_tag)
        self.assertIn("data-product-card-deferred-image", third_tag)
        self.assertNotIn(" src=", third_tag)

        first_picture_start = html.rindex("<picture>", 0, first_start)
        first_source_start = html.index("<source", first_picture_start)
        first_source_end = html.index(">", first_source_start)
        first_source_tag = html[first_source_start:first_source_end]
        self.assertIn('media="(min-width: 1024px)" srcset=', first_source_tag)
        self.assertNotIn("data-srcset=", first_source_tag)

        third_picture_start = html.rindex("<picture>", 0, third_start)
        third_source_start = html.index("<source", third_picture_start)
        third_source_end = html.index(">", third_source_start)
        third_source_tag = html[third_source_start:third_source_end]
        self.assertIn('media="(min-width: 1024px)" data-srcset=', third_source_tag)

        deferred_marker = '<img class="product-tile__image__primary" data-product-card-deferred-image data-src="https://cdn.shopify.com/s/files/1/0998/6780/files/TheDoubleDropCubicPendantNecklace.jpg'
        self.assertNotIn(deferred_marker, html)
        self.assertIn(deferred_marker, fragment_html)
        deferred_start = fragment_html.index(deferred_marker)
        deferred_end = fragment_html.index(">", deferred_start)
        deferred_tag = fragment_html[deferred_start:deferred_end]
        self.assertNotIn(" src=", deferred_tag)
        self.assertIn("data-srcset=", deferred_tag)

        deferred_picture_start = fragment_html.rindex("<picture>", 0, deferred_start)
        deferred_source_start = fragment_html.index("<source", deferred_picture_start)
        deferred_source_end = fragment_html.index(">", deferred_source_start)
        deferred_source_tag = fragment_html[deferred_source_start:deferred_source_end]
        self.assertIn("&amp;width=540 540w", deferred_source_tag)
        self.assertNotIn("&amp;width=760", deferred_source_tag)

    def test_collection_initial_html_defers_offscreen_product_cards(self):
        response = self.client.get("/store/collections/new-arrivals")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('data-results-count="48"', html)
        self.assertIn('data-collection-grid', html)
        self.assertIn('data-collection-deferred-products', html)
        self.assertIn('/store/collections/new-arrivals/products-fragment?offset=12', html)
        self.assertIn('data-product-handle="the-salt-pepper-cylinder-necklace-set"', html)
        self.assertNotIn('data-product-handle="the-double-drop-cubic-pendant"', html)
        self.assertLess(len(response.get_data()), 95000)

    def test_collection_products_fragment_returns_remaining_cards(self):
        response = self.client.get("/store/collections/new-arrivals/products-fragment?offset=12")
        self.addCleanup(response.close)

        self.assertEqual(response.status_code, 200)
        self.assertIn("public", response.headers.get("Cache-Control", ""))
        self.assertIn("max-age=3600", response.headers.get("Cache-Control", ""))
        html = response.get_data(as_text=True)
        self.assertIn('data-product-handle="the-short-snake-chain-necklace"', html)
        self.assertIn('data-product-handle="the-double-drop-cubic-pendant"', html)
        self.assertNotIn('data-product-handle="the-salt-pepper-cylinder-necklace-set"', html)
        self.assertIn("data-product-card-deferred-image", html)

    def test_product_card_deferred_images_hydrate_after_scroll_or_pointer(self):
        source = (pocket.BASE_DIR / "pages" / "store" / "store.js").read_text(encoding="utf-8")

        self.assertIn("function hydrateVisibleProductCardImages()", source)
        self.assertIn("function bindDeferredProductCardImageHydration()", source)
        self.assertIn("function bindDeferredCollectionProducts()", source)
        self.assertIn("[data-collection-deferred-products]", source)
        self.assertIn("fetch(sentinel.dataset.fragmentUrl)", source)
        self.assertIn("[data-product-card-deferred-image][data-src]", source)
        self.assertIn('window.addEventListener("scroll"', source)
        self.assertIn('window.addEventListener("pointerdown"', source)
        self.assertIn("hydrateDeferredImage(image);", source)
        self.assertIn("bindDeferredProductCardImageHydration();", source)

    def test_homepage_uses_live_desktop_split_assets_and_custom_category_link(self):
        response = self.client.get("/store")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("0526_Hearts.jpg", html)
        self.assertIn("0531_HappyBaby_Mobile_9f30ae56-b0cc-48f3-9f88-28ec80b99883.jpg", html)
        self.assertIn("0531_Camp_Mobile_55bf818c-5e28-4609-93ff-1e7bf5a090d6.jpg", html)
        self.assertIn("0531_ItsyBitsy_Mobile_47e7a0a7-064e-44fb-b14e-5971f5c14833.jpg", html)
        self.assertIn("href=\"/store/collections/custom\"", html)

    def test_homepage_defers_below_fold_home_section_images_for_lighthouse(self):
        response = self.client.get("/store")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        first_hero_img_start = html.index('<img src="https://roxanneassoulin.com/cdn/shop/files/0531_MainImage_Mobile')
        first_hero_img_end = html.index(">", first_hero_img_start)
        first_hero_img_tag = html[first_hero_img_start:first_hero_img_end]
        self.assertIn(" src=", first_hero_img_tag)
        self.assertIn('fetchpriority="high"', first_hero_img_tag)

        deferred_marker = '<img data-home-deferred-image data-src="https://roxanneassoulin.com/cdn/shop/files/0531_HappyBaby_Mobile_9f30ae56-b0cc-48f3-9f88-28ec80b99883.jpg'
        self.assertIn(deferred_marker, html)
        deferred_start = html.index(deferred_marker)
        deferred_end = html.index(">", deferred_start)
        deferred_tag = html[deferred_start:deferred_end]
        self.assertIn("data-src=", deferred_tag)
        self.assertIn("data-srcset=", deferred_tag)
        self.assertIn("data-sizes=", deferred_tag)
        self.assertIn("&amp;width=420", deferred_tag)
        self.assertNotIn("&amp;width=480", deferred_tag)
        self.assertNotIn(" src=", deferred_tag)
        self.assertNotIn(" srcset=", deferred_tag)

        split_marker = '<img data-home-deferred-image data-src="https://roxanneassoulin.com/cdn/shop/files/0526_Hearts.jpg'
        self.assertIn(split_marker, html)
        split_start = html.index(split_marker)
        split_end = html.index(">", split_start)
        split_tag = html[split_start:split_end]
        self.assertNotIn(" src=", split_tag)
        self.assertIn("&amp;width=420", split_tag)
        self.assertNotIn("&amp;width=760", split_tag)
        self.assertNotIn("&amp;width=1200 1200w", split_tag)
        self.assertIn('data-sizes="(min-width: 1024px) 50vw, 100vw"', split_tag)

    def test_homepage_deferred_images_hydrate_after_scroll_or_pointer(self):
        source = (pocket.BASE_DIR / "pages" / "store" / "store.js").read_text(encoding="utf-8")

        self.assertIn("function hydrateVisibleHomeImages()", source)
        self.assertIn("function bindDeferredHomeImageHydration()", source)
        self.assertIn("[data-home-deferred-image][data-src]", source)
        self.assertIn('window.addEventListener("scroll"', source)
        self.assertIn('window.addEventListener("pointerdown"', source)
        self.assertIn("hydrateDeferredImage(image);", source)
        self.assertIn("bindDeferredHomeImageHydration();", source)

    def test_custom_collection_alias_matches_live_homepage_link(self):
        response = self.client.get("/store/collections/custom")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("custom", html.lower())
        self.assertIn("product-tile", html)

    def test_homepage_exposes_live_shells_and_product_tile_controls(self):
        response = self.client.get("/store")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('role="main" id="main" class="content"', html)
        self.assertIn('class="home" data-view="home"', html)
        self.assertIn("shopify-section", html)
        self.assertIn("hero__image", html)
        self.assertIn("hero__cta", html)
        self.assertIn("product-tile js-productTile", html)
        self.assertIn("product-tile__top", html)
        self.assertIn("product-tile__copy__wrapper", html)
        self.assertIn("product-tile__add js-quickshopOpen", html)
        self.assertIn("search-drawer js-searchDrawer", html)
        self.assertIn("cart-notification js-cartNotificationDrawer", html)
        self.assertIn("promo js-promo", html)
        self.assertIn("quickshop__drawer js-quickshopDrawer", html)
        self.assertIn("footer-newsletter__social", html)
        self.assertIn("footer__bottom", html)
        self.assertIn("Legal", html)

    def test_collection_page_renders_products(self):
        response = self.client.get("/store/collections/necklaces")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("Necklaces", html)
        self.assertIn("data-quickshop-open", html)

    def test_collection_hero_uses_responsive_shopify_image_delivery(self):
        response = self.client.get("/store/collections/new-arrivals")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("collection-hero__image", html)
        self.assertIn("&amp;width=760 760w", html)
        self.assertIn("&amp;width=1200 1200w", html)
        self.assertIn('sizes="50vw"', html)
        self.assertIn('src="https://roxanneassoulin.com/cdn/shop/collections/New-Arrivals.jpg?v=1779127477&amp;quality=60&amp;width=390"', html)
        self.assertIn('sizes="100vw"', html)

    def test_product_page_renders_variant_add_to_cart(self):
        product, variant = self.first_available_variant()
        response = self.client.get(f"/store/products/{product['handle']}")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn(html_lib.escape(product["title"]), html)
        self.assertIn(str(variant["id"]), html)
        self.assertIn("data-product-form", html)

    def test_product_page_renders_body_html_as_short_description(self):
        product = next(
            item for item in pocket.load_store_catalog().get("products", [])
            if item.get("body_html")
        )

        response = self.client.get(f"/store/products/{product['handle']}")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("product-short-description", html)
        self.assertIn("Description", html)
        self.assertIn("data-product-description", html)

    def test_store_base_exposes_menu_and_cart_drawers(self):
        response = self.client.get("/store")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("class=\"site-header header\"", html)
        self.assertIn("header__toggle", html)
        self.assertIn("header__logo", html)
        self.assertIn("data-menu-drawer", html)
        self.assertIn("data-menu-toggle", html)
        self.assertIn("data-cart-drawer", html)
        self.assertIn("data-cart-open", html)
        self.assertIn("data-cart-drawer-lines", html)

    def test_menu_open_state_has_body_scoped_visibility_override(self):
        source = self.store_css_source()

        self.assertIn('.drawer-is-open .menu-drawer[aria-hidden="false"]', source)
        self.assertIn("transform: translateX(0) !important", source)
        self.assertIn("visibility: visible !important", source)

    def test_menu_drawer_overrides_critical_hidden_height_when_open(self):
        source = self.store_css_source()

        self.assertIn(".menu-drawer {\n      background: var(--blue);", source)
        self.assertIn("height: 100dvh;", source)
        self.assertIn("overflow-y: auto;", source)

    def test_menu_drawer_uses_runtime_transform_visibility_guard(self):
        source = (pocket.BASE_DIR / "pages" / "store" / "store.js").read_text(encoding="utf-8")

        self.assertIn("function setMenuDrawerVisibility", source)
        self.assertIn('drawer.style.setProperty("transition", "none", "important")', source)
        self.assertIn('drawer.style.setProperty("transform", "translateX(0)", "important")', source)
        self.assertIn("setMenuDrawerVisibility(drawer, false)", source)

    def test_store_base_splits_mobile_cart_page_and_desktop_drawer_controls(self):
        response = self.client.get("/store")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("header__cart--drawer", html)
        self.assertIn("header__cart--page", html)
        self.assertIn('href="/store/cart"', html)
        self.assertIn('aria-controls="cart-drawer"', html)
        self.assertIn("cart-drawer__overlay", html)

    def test_store_base_exposes_live_search_drawer_controls(self):
        response = self.client.get("/store")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('aria-controls="search-drawer"', html)
        self.assertIn("data-search-open", html)
        self.assertIn("data-search-close", html)
        self.assertIn("search-drawer__form", html)

    def test_search_open_state_has_body_scoped_visibility_override(self):
        source = self.store_css_source()

        self.assertIn('.search-is-open .search-drawer[aria-hidden="false"]', source)
        self.assertIn("opacity: 1 !important", source)
        self.assertIn("visibility: visible !important", source)

    def test_desktop_header_renders_live_search_login_about_cluster(self):
        response = self.client.get("/store")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        source = self.store_css_source()
        self.assertIn('class="header-extra desktop-visible"', html)
        self.assertIn(">Login</a>", html)
        self.assertIn(">About</a>", html)
        self.assertIn(".header-extra {\n      display: none;", source)
        self.assertIn(".store-search {\n        display: block;\n        height: 50px;\n        right: 209px;", source)
        self.assertIn(".header-extra {\n        align-items: center;\n        display: flex !important;\n        gap: 22px;", source)

    def test_store_uses_live_theme_product_tile_structure(self):
        response = self.client.get("/store/collections/the-summer-capsule")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("product-tile", html)
        self.assertIn("product-tile__image", html)
        self.assertIn("product-tile__image__hover", html)
        self.assertIn("product-tile__title", html)
        self.assertIn("product-tile__add", html)

    def test_product_tiles_use_live_quickshop_button_not_inline_variant_select(self):
        response = self.client.get("/store/collections/new-arrivals")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('class="product-tile__add js-quickshopOpen"', html)
        self.assertIn('<span class="visually-hidden">open quick shop</span>', html)
        self.assertIn('viewBox="0 0 24 24"', html)
        self.assertIn('data-quickshop-open', html)
        self.assertNotIn('data-variant-select', html)
        self.assertNotIn('class="product-tile__add js-quickshopOpen" type="button" data-store-add', html)

    def test_product_tile_desktop_copy_band_matches_live_overlay_geometry(self):
        source = self.store_css_source()

        self.assertIn(".product-tile__copy__wrapper {\n        left: 3px;\n        right: 3px;\n        bottom: 2px;\n        grid-template-columns: minmax(0, 1fr) 76px;", source)
        self.assertIn(".product-tile__add {\n        border-radius: 0;\n        height: auto;\n        min-height: 76px;\n        width: 76px;", source)

    def test_product_tile_desktop_copy_typography_matches_live_band(self):
        source = self.store_css_source()

        self.assertIn("left: 3px;\n        right: 3px;\n        bottom: 2px;", source)
        self.assertIn(".product-tile__copy {\n        padding: 17px 20px;", source)
        self.assertIn(".product-tile__title {\n        font-size: .875rem;\n        line-height: 135%;\n        padding: 0 0 4px;", source)
        self.assertIn(".product-tile__price {\n        font-size: .875rem;\n        line-height: 135%;\n        padding: 0;", source)

    def test_quickshop_drawer_has_live_content_shell_and_script_hooks(self):
        response = self.client.get("/store")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        source = (pocket.BASE_DIR / "pages" / "store" / "store.js").read_text(encoding="utf-8")
        self.assertIn("quickshop__content", html)
        self.assertIn("quickshop__content__top js-productDetailsTop", html)
        self.assertIn("quickshop__content__image js-productDetailsImage", html)
        self.assertIn("quickshop__content__details js-productDetailsContent", html)
        self.assertIn("data-quickshop-close", html)
        self.assertIn("openQuickshopDrawer", source)
        self.assertIn("renderQuickshop", source)
        self.assertIn("[data-quickshop-open]", source)
        self.assertIn("[data-quickshop-add]", source)
        self.assertIn("quickshop-is-open", source)

    def test_quickshop_open_state_has_body_scoped_transform_override(self):
        source = self.store_css_source()

        self.assertIn('.quickshop-is-open .quickshop__drawer[aria-hidden="false"]', source)
        self.assertIn("transform: translateY(0) !important", source)

    def test_store_price_labels_match_live_euro_market(self):
        product = pocket.store_product_by_handle("the-cylinder-cord-necklace-cloud-blue")
        variant = pocket.store_first_available_variant(product)

        self.assertEqual(pocket.store_variant_price_label(variant), "\u20ac109,95")
        self.assertNotIn("$125", pocket.store_price_label(product))

    def test_store_price_ranges_use_live_market_dash_and_conversion(self):
        product = pocket.store_product_by_handle("the-salt-pepper-cylinder-necklace-set")

        self.assertEqual(pocket.store_price_label(product), "\u20ac109,95 \u2013 \u20ac393,95")

    def test_store_frontend_exposes_live_market_price_settings(self):
        response = self.client.get("/store")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('data-store-display-currency="eur"', html)
        self.assertIn('data-store-display-eur-rate="0.875"', html)

    def test_store_frontend_script_uses_live_market_price_formatting(self):
        source = (pocket.BASE_DIR / "pages" / "store" / "store.js").read_text(encoding="utf-8")

        self.assertIn("formatDisplayPrice", source)
        self.assertIn("displayCurrency", source)
        self.assertIn("convertedWholeUnits", source)

    def test_product_tiles_hide_quick_add_on_mobile_like_live_theme(self):
        source = self.store_css_source()

        self.assertIn(".product-tile__add", source)
        self.assertIn("display: none", source)
        self.assertIn("@media (min-width: 1024px)", source)
        self.assertIn("display: inline-flex", source)
        self.assertNotIn("min-height: 96px", source)

    def test_product_tiles_do_not_render_catalog_badge_tags_like_live_theme(self):
        response = self.client.get("/store/collections/necklaces")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertNotIn("product-tile__badge", html)
        self.assertNotIn(">new<", html)

    def test_collection_page_exposes_filter_and_sort_drawers(self):
        response = self.client.get("/store/collections/the-summer-capsule")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("collection-filter__bar", html)
        self.assertIn("collection-filter__drawer--filter", html)
        self.assertIn("collection-filter__drawer--sort", html)
        self.assertIn("data-filter-toggle", html)
        self.assertIn("data-sort-toggle", html)

    def test_collection_page_uses_live_collection_grid_controls_and_pagination(self):
        response = self.client.get("/store/collections/necklaces")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('class="collection" data-view="collection"', html)
        self.assertIn("collection-items", html)
        self.assertIn("data-results-count", html)
        self.assertIn("collection-filter__bar__button", html)
        self.assertIn("js-filterToggle", html)
        self.assertIn("collection-filter__overlay js-filterOverlay js-filterClose", html)
        self.assertIn('method="GET"', html)
        self.assertIn("js-filterOption", html)
        self.assertIn("filter.p.product_type", html)
        self.assertIn("collection-filter__sort", html)
        self.assertIn("?sort_by=created-descending", html)
        self.assertIn("pagination", html)

    def test_collection_mobile_hero_and_filter_match_live_geometry(self):
        source = self.store_css_source()

        self.assertIn(".collection-hero {\n      position: relative;\n      padding: 0;", source)
        self.assertIn(".collection-filter-bar button", source)
        self.assertIn("height: 74px", source)
        self.assertIn("font-size: 1rem", source)
        self.assertIn("font-weight: 400", source)
        self.assertIn("text-transform: none", source)

    def test_collection_controls_use_live_label_casing_and_icons(self):
        response = self.client.get("/store/collections/new-arrivals")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("Filter", html)
        self.assertIn("Sort", html)
        self.assertIn("M4 2v10", html)
        self.assertIn("M7 2v10", html)

    def test_collection_desktop_hero_flows_inside_live_product_grid(self):
        source = self.store_css_source()

        self.assertIn(".collection-items {\n        display: grid;\n        grid-template-columns: repeat(4, minmax(0, 1fr));\n        padding-top: 72px;", source)
        self.assertIn("grid-column: 1 / -1;\n        height: 76px;\n        order: -1;\n        top: 72px;", source)
        self.assertIn(".collection-grid {\n        display: contents;", source)
        self.assertIn(".collection-hero {\n        grid-column: 1 / span 2;\n        grid-row: span 2;\n        height: 765px;", source)
        self.assertIn(".product-tile {\n        height: 384px;", source)

    def test_collection_desktop_filter_bar_matches_live_inset_controls(self):
        source = self.store_css_source()

        self.assertIn(".collection-filter-bar {\n        background: transparent;\n        display: flex;", source)
        self.assertIn("top: 72px;\n        z-index: 12;", source)
        self.assertIn(".collection-filter__bar__button {\n        flex: 0 0 calc(50% - 4px);\n        height: 75px;\n        margin-left: 0;", source)
        self.assertIn("margin-left: 0;\n        margin-top: 1px;", source)
        self.assertIn(".collection-filter__bar__button:first-child {\n        margin-left: 9px;", source)
        self.assertIn(".collection-filter-bar button {\n        display: block;\n        height: 55px;\n        margin-top: 5px;", source)
        self.assertIn("padding: 0 12px;\n        text-align: center;\n        width: calc(100% - 9px);", source)

    def test_collection_filter_drawer_uses_live_inner_structure(self):
        response = self.client.get("/store/collections/necklaces")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("collection-filter__drawer__head", html)
        self.assertIn("collection-filter__drawer__scroll", html)
        self.assertIn("collection-filter__options", html)
        self.assertIn('<strong id="filter-p-product_type-heading">Category</strong>', html)
        self.assertIn('<ul aria-labelledby="filter-p-product_type-heading">', html)
        self.assertIn('id="filter-p-product_type1"', html)
        self.assertIn('for="filter-p-product_type1">Bracelets</label>', html)
        self.assertNotIn("<fieldset", html)
        self.assertNotIn("collection-filter__checkbox", html)
        self.assertIn("collection-filter__buttons", html)
        self.assertIn(">Apply<", html)

    def test_collection_filter_drawer_uses_live_color_facets(self):
        response = self.client.get("/store/collections/new-arrivals")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        expected_colors = [
            "Black",
            "Blue",
            "Brown",
            "Diamond",
            "Gold",
            "Lemon",
            "Multi",
            "Orange",
            "Rainbow",
            "Red",
            "White",
            "Yellow",
        ]
        for index, color in enumerate(expected_colors, start=1):
            with self.subTest(color=color):
                self.assertIn(f'id="filter-p-m-roxanne-assoulin-filter_color{index}"', html)
                self.assertIn(f'value="{color}"', html)
                self.assertIn(f'for="filter-p-m-roxanne-assoulin-filter_color{index}">{color}</label>', html)
        self.assertNotIn('value="Charms"', html)
        self.assertNotIn('value="green"', html)
        self.assertNotIn('value="pink"', html)

    def test_collection_product_tile_uses_live_full_card_link_and_picture(self):
        response = self.client.get("/store/collections/new-arrivals")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('<a href="/store/products/the-salt-pepper-cylinder-necklace-set" class="product-tile__link">', html)
        self.assertIn("<picture>", html)
        self.assertIn('class="product-tile__image__primary"', html)
        self.assertIn('class="product-tile__image__hover is-loading"', html)
        self.assertNotIn('<a class="product-tile__image"', html)

    def test_product_tile_hover_images_defer_network_until_interaction(self):
        response = self.client.get("/store/collections/new-arrivals")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        hover_start = html.index('<img class="product-tile__image__hover is-loading"')
        hover_end = html.index(">", hover_start)
        hover_tag = html[hover_start:hover_end]
        self.assertIn("data-src=", hover_tag)
        self.assertIn("data-srcset=", hover_tag)
        self.assertIn("data-sizes=", hover_tag)
        self.assertNotIn("&amp;width=760", hover_tag)
        self.assertNotIn(" src=", hover_tag)
        self.assertNotIn(" srcset=", hover_tag)

    def test_product_tile_primary_mobile_srcset_avoids_desktop_width(self):
        response = self.client.get("/store/collections/new-arrivals")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        primary_start = html.index('<img class="product-tile__image__primary"')
        primary_end = html.index(">", primary_start)
        primary_tag = html[primary_start:primary_end]
        self.assertIn("&amp;width=240 240w", primary_tag)
        self.assertIn("&amp;width=360 360w", primary_tag)
        self.assertIn("&amp;width=390 390w", primary_tag)
        self.assertNotIn("&amp;width=480 480w", primary_tag)
        self.assertNotIn("&amp;width=540", primary_tag)
        self.assertNotIn("&amp;width=760", primary_tag)
        self.assertIn('sizes="(min-width: 1024px) 25vw, 50vw"', primary_tag)

    def test_home_product_tiles_keep_wider_mobile_card_candidate(self):
        response = self.client.get("/store")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        module_start = html.index('<section class="shopify-section product-module">')
        primary_start = html.index('<img class="product-tile__image__primary"', module_start)
        primary_end = html.index(">", primary_start)
        primary_tag = html[primary_start:primary_end]
        self.assertIn("&amp;width=540 540w", primary_tag)

    def test_product_tile_hover_loader_preserves_desktop_hover_behavior(self):
        source = (pocket.BASE_DIR / "pages" / "store" / "store.js").read_text(encoding="utf-8")
        css = self.store_css_source()

        self.assertIn("hydrateProductTileHoverImage", source)
        self.assertIn(".product-tile__image__hover.is-loaded", css)
        self.assertIn('document.addEventListener("pointerover"', source)
        self.assertIn('document.addEventListener("mouseover"', source)
        self.assertIn('document.addEventListener("focusin"', source)

    def test_key_collection_pages_use_extracted_live_hero_assets(self):
        cases = {
            "necklaces": "Necklaces.jpg",
            "new-arrivals": "New-Arrivals.jpg",
        }

        for handle, image_token in cases.items():
            with self.subTest(handle=handle):
                response = self.client.get(f"/store/collections/{handle}")

                self.assertEqual(response.status_code, 200)
                html = response.get_data(as_text=True)
                self.assertIn("collection-hero", html)
                self.assertIn(image_token, html)

    def test_collection_pages_use_live_merchandising_counts_and_pagination(self):
        necklaces = self.client.get("/store/collections/necklaces").get_data(as_text=True)
        new_arrivals = self.client.get("/store/collections/new-arrivals").get_data(as_text=True)

        self.assertIn('data-results-count="173"', necklaces)
        self.assertIn("1 of 4", necklaces)
        self.assertIn("pagination__next", necklaces)
        self.assertIn('data-results-count="48"', new_arrivals)
        self.assertNotIn("pagination__next", new_arrivals)

    def test_new_arrivals_collection_uses_live_ordered_first_product(self):
        response = self.client.get("/store/collections/new-arrivals")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        collection, products = pocket.store_collection_products("new-arrivals")
        handles = [product["handle"] for product in products]

        self.assertEqual(collection["results_count"], 48)
        self.assertEqual(len(products), 48)
        self.assertEqual(
            handles[:5],
            [
                "the-salt-pepper-cylinder-necklace-set",
                "the-cylinder-cord-bracelet-sienna-orange",
                "the-cylinder-cord-necklace-cloud-blue",
                "the-salt-pepper-cylinder-bracelet-stack",
                "the-cylinder-cord-necklace-lemon-yellow",
            ],
        )
        self.assertLess(
            html.index('data-product-handle="the-cylinder-cord-bracelet-sienna-orange"'),
            html.index('data-product-handle="the-cylinder-cord-necklace-lemon-yellow"'),
        )

    def test_collection_price_sort_reorders_products(self):
        response = self.client.get("/store/collections/necklaces?sort_by=price-ascending")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        cheapest = html.index('data-product-handle="the-happy-cord-charm-necklace-blood-orange-red"')
        curated = html.index('data-product-handle="the-salt-pepper-cylinder-necklace-set"')
        self.assertLess(cheapest, curated)

    def test_collection_color_filter_filters_products_and_preserves_checked_state(self):
        response = self.client.get("/store/collections/necklaces?filter.p.m.roxanne-assoulin.filter_color%5B%5D=Yellow")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('data-results-count="4"', html)
        self.assertIn('data-product-handle="the-salt-pepper-cylinder-necklace-set"', html)
        self.assertIn('data-product-handle="the-cylinder-cord-necklace-lemon-yellow"', html)
        self.assertIn('data-product-handle="the-itsy-bitsy-puffy-heart-charms"', html)
        self.assertIn('data-product-handle="tiny-treasure-charms"', html)
        self.assertNotIn('data-product-handle="the-cylinder-cord-necklace-cloud-blue"', html)
        self.assertIn('name="filter.p.m.roxanne-assoulin.filter_color[]" type="checkbox" value="Yellow" checked', html)
        self.assertNotIn("pagination__next", html)

    def test_collection_category_filter_filters_custom_collection_and_preserves_checked_state(self):
        response = self.client.get("/store/collections/custom?filter.p.product_type%5B%5D=Bracelets")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('data-product-handle="the-cylinder-cord-bracelet-lemon-yellow"', html)
        self.assertNotIn('data-product-handle="the-cylinder-cord-necklace-lemon-yellow"', html)
        self.assertIn('name="filter.p.product_type[]" type="checkbox" value="Bracelets" checked', html)
        self.assertIn("type=\"submit\"", html)

    def test_shop_collection_search_query_filters_products_and_preserves_input(self):
        response = self.client.get("/store/collections/shop?q=paprika")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('data-results-count="4"', html)
        self.assertIn('value="paprika"', html)
        self.assertIn('data-product-handle="the-paprika-necklace-duo"', html)
        self.assertIn('data-product-handle="the-netted-stone-pendant"', html)
        self.assertIn('data-product-handle="the-paprika-bracelet-duo"', html)
        self.assertIn('data-product-handle="the-crimp-bracelet"', html)
        self.assertNotIn('data-product-handle="the-salt-pepper-cylinder-necklace-set"', html)
        self.assertNotIn("pagination__next", html)

    def test_collection_sort_links_preserve_search_and_filter_state(self):
        response = self.client.get(
            "/store/collections/necklaces?q=lemon&filter.p.m.roxanne-assoulin.filter_color%5B%5D=Yellow"
        )

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn(
            'href="?q=lemon&amp;filter.p.m.roxanne-assoulin.filter_color%5B%5D=Yellow&amp;sort_by=price-ascending"',
            html,
        )
        self.assertIn(
            'href="?q=lemon&amp;filter.p.m.roxanne-assoulin.filter_color%5B%5D=Yellow&amp;sort_by=price-descending"',
            html,
        )

    def test_store_base_renders_live_style_footer(self):
        response = self.client.get("/store")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("class=\"footer\"", html)
        self.assertIn("footer__colors", html)
        self.assertIn("footer-newsletter", html)
        self.assertIn("footer-nav__tabset", html)

    def test_store_mobile_footer_starts_from_collapsed_live_state(self):
        source = self.store_css_source()

        self.assertIn(".footer-nav__panel {\n      display: none;", source)
        self.assertIn(".footer-nav__panel {\n        display: block;", source)
        self.assertIn("min-height: 638px", source)

    def test_store_footer_uses_live_mobile_newsletter_copy(self):
        response = self.client.get("/store")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn(">Subscribe<", html)
        self.assertIn("Already a friend?", html)
        self.assertIn("Login", html)
        self.assertIn("\u00a9 Roxanne Assoulin 2026. All rights reserved", html)
        self.assertNotIn("Prototype storefront", html)

    def test_product_page_exposes_gallery_variant_and_quantity_hooks(self):
        product, variant = self.first_available_variant()
        response = self.client.get(f"/store/products/{product['handle']}")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("data-gallery-dot", html)
        self.assertIn("data-pdp-variant-select", html)
        self.assertIn("data-product-qty", html)
        self.assertIn("data-qty-inc", html)
        self.assertIn("data-qty-dec", html)

    def test_product_page_uses_live_pdp_structure_and_buy_options(self):
        product, _variant = self.first_available_variant()
        response = self.client.get(f"/store/products/{product['handle']}")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("product-info", html)
        self.assertIn("product-gallery__wrapper", html)
        self.assertIn("product-gallery__image__wrapper", html)
        self.assertIn("product-details", html)
        self.assertIn("product-details-top__name", html)
        self.assertIn("product-details-bottom__col--options", html)
        self.assertIn("product-buy-options", html)
        self.assertIn("product-buy-options__add-wrapper", html)
        self.assertIn("product-buy-options__price", html)
        self.assertIn("js-addToBag", html)
        self.assertIn("button--blue", html)
        source = self.store_css_source()
        self.assertIn(".product-buy-options__add-wrapper button", source)
        self.assertIn("height: 60px", source)

    def test_product_page_exposes_custom_option_drawer_and_lightbox(self):
        product = pocket.store_product_by_handle("the-salt-pepper-cylinder-necklace-set")
        response = self.client.get(f"/store/products/{product['handle']}")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("data-option-trigger", html)
        self.assertIn("data-option-selected-title", html)
        self.assertIn("data-option-drawer", html)
        self.assertIn("data-option-choice", html)
        self.assertIn("option-selector__native", html)
        self.assertIn("data-product-lightbox", html)
        self.assertIn("data-lightbox-open", html)
        self.assertIn("data-lightbox-image", html)
        self.assertIn("data-lightbox-close", html)

    def test_price_pill_uses_selected_variant_price_for_price_ranges(self):
        product = pocket.store_product_by_handle("the-salt-pepper-cylinder-necklace-set")
        first_variant = pocket.store_pdp_variant_options(product)[0]["variant"]
        response = self.client.get(f"/store/products/{product['handle']}")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn(f'data-selected-price="{pocket.store_variant_price_label(first_variant)}"', html)
        self.assertIn(f'product-buy-options__price">{pocket.store_variant_price_label(first_variant)}</div>', html)
        self.assertNotIn('product-buy-options__price">$125.00 - $450.00</div>', html)

    def test_cloud_blue_product_promotes_live_lifestyle_image_first(self):
        response = self.client.get("/store/products/the-cylinder-cord-necklace-cloud-blue")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        lifestyle_index = html.index("THE_CYLINDER_CORD_NECKLACE_2495")
        flat_index = html.index("CylinderCordNecklace_Cloud_1")
        self.assertLess(lifestyle_index, flat_index)

    def test_cloud_blue_product_uses_live_merchandising_copy(self):
        response = self.client.get("/store/products/the-cylinder-cord-necklace-cloud-blue")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("Your no-sweat summer showpiece", html)
        self.assertIn('Approximately 15" necklace', html)
        self.assertIn("The Happy Pearl Necklace in Espresso", html)
        self.assertIn("The Salt &amp; Pepper Necklace Duo", html)

    def test_product_page_renders_live_details_top_product_image(self):
        response = self.client.get("/store/products/the-cylinder-cord-necklace-cloud-blue")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        source = self.store_css_source()
        self.assertIn("product-details-top__image", html)
        self.assertIn("data-product-details-image", html)
        self.assertIn("CylinderCordNecklace_Cloud_1", html)
        self.assertIn(".product-details-top__image", source)

    def test_product_page_uses_responsive_shopify_image_delivery(self):
        response = self.client.get("/store/products/the-cylinder-cord-necklace-cloud-blue")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("product-gallery__image__wrapper", html)
        self.assertIn("&amp;width=760 760w", html)
        self.assertIn("&amp;width=1200 1200w", html)
        self.assertIn('sizes="50vw"', html)
        self.assertIn('sizes="100vw"', html)
        self.assertIn('sizes="(min-width: 1024px) 320px, 42vw"', html)

    def test_product_javascript_updates_details_top_image_for_variant_switch(self):
        source = (pocket.BASE_DIR / "pages" / "store" / "store.js").read_text(encoding="utf-8")

        self.assertIn("[data-product-details-image]", source)
        self.assertIn("selected.dataset.imageSrc", source)

    def test_product_merchandising_uses_live_motto_then_description_table_order(self):
        response = self.client.get("/store/products/the-cylinder-cord-necklace-cloud-blue")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("<th scope=\"row\">Description</th>", html)
        self.assertLess(html.index("Your no-sweat summer showpiece"), html.index("<th scope=\"row\">Description</th>"))
        self.assertNotIn('class="product-short-description"', html)

    def test_product_css_matches_live_mobile_buy_box_spacing(self):
        source = self.store_css_source()

        self.assertIn(".product-details-bottom__col--options {\n      border-bottom: 1px solid #e6e6e6;\n      order: 1;\n      padding-bottom: 0;\n      padding-top: 0;", source)
        self.assertIn("padding: 10px 0 22px;", source)
        self.assertIn("padding: 0 0 16px;", source)

    def test_product_css_matches_live_desktop_gallery_depth(self):
        source = self.store_css_source()

        self.assertIn(".product-gallery__image__wrapper:nth-child(n+3) {\n        display: none;", source)
        self.assertIn(".product-gallery__zoom picture {\n      display: block;\n      height: 100%;\n      width: 100%;", source)
        self.assertIn(".product-page {\n        padding: 0;", source)
        self.assertIn(".product-info {\n        min-height: 1604px;\n        padding-top: 72px;", source)
        self.assertIn(".product-related-section {\n        height: 631px;\n        padding: 0;", source)
        self.assertIn(".product-related-section > * {\n        display: none;", source)
        self.assertIn(".product-details-top__images {\n        height: 300px;", source)
        self.assertIn(".product-details-top__image,\n      .product-details-top__image img {\n        height: 300px;\n        width: 300px;", source)
        self.assertIn(".product-details-top__name {\n        max-width: 328px;\n        white-space: nowrap;\n        width: 328px;", source)
        self.assertIn(".buy-box .product-details-top__name {\n        max-width: 328px;\n        width: 328px;", source)

    def test_product_page_gallery_starts_under_live_overlay_header(self):
        response = self.client.get("/store/products/the-cylinder-cord-necklace-cloud-blue")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        source = self.store_css_source()
        self.assertIn('class="page product-page"', html)
        self.assertIn(".product-page {\n      padding-top: 5px;", source)

    def test_product_page_uses_live_add_to_bag_and_shipping_copy(self):
        response = self.client.get("/store/products/the-cylinder-cord-necklace-cloud-blue")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        source = self.store_css_source()
        self.assertIn(">Add to Bag<", html)
        self.assertIn("Enjoy complimentary ground shipping on US orders $250+", html)
        self.assertIn("text-transform: none;", source)
        self.assertNotIn("Prototype checkout verifies", html)

    def test_product_page_uses_live_related_heading(self):
        response = self.client.get("/store/products/the-cylinder-cord-necklace-cloud-blue")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("THE MORE THE BETTER", html)
        self.assertIn("product-related-section", html)
        self.assertNotIn("you may also like", html)

    def test_cart_page_renders_checkout_hooks(self):
        response = self.client.get("/store/cart")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("data-cart-page", html)
        self.assertIn("/store/api/checkout", html)

    def test_checkout_success_redirects_directly_to_shopify_cart(self):
        source = (pocket.BASE_DIR / "pages" / "store" / "store.js").read_text(encoding="utf-8")

        self.assertIn("window.location.href = data.shopify_cart_url", source)
        self.assertNotIn("Open Shopify cart", source)

    def test_cart_page_uses_live_cart_structure(self):
        response = self.client.get("/store/cart")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("class=\"cart\" data-view=\"cart\"", html)
        self.assertIn("cart-page", html)
        self.assertIn("cart-page__items", html)
        self.assertIn("cart-page__summary", html)
        self.assertIn('<a class="cart-page__checkout" href="/checkout" data-checkout>Checkout</a>', html)
        self.assertNotIn("<button class=\"cart-page__checkout\"", html)

    def test_cart_page_renders_live_selected_for_u_upsells(self):
        response = self.client.get("/store/cart")
        fragment_response = self.client.get("/store/cart-upsells-fragment")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(fragment_response.status_code, 200)
        html = response.get_data(as_text=True)
        fragment_html = fragment_response.get_data(as_text=True)
        self.assertIn("public", fragment_response.headers.get("Cache-Control", ""))
        self.assertIn("max-age=3600", fragment_response.headers.get("Cache-Control", ""))
        self.assertIn("data-cart-page-upsell-fragment", html)
        self.assertIn('/store/cart-upsells-fragment', html)
        self.assertNotIn('<section class="cart-upsell shopify-section"', html)
        self.assertNotIn("selected for u", html)
        self.assertNotIn('data-product-handle="the-salt-pepper-cylinder-bracelet-stack"', html)
        self.assertIn("cart-upsell", fragment_html)
        self.assertIn("selected for u", fragment_html)
        self.assertIn('data-product-handle="the-salt-pepper-cylinder-bracelet-stack"', fragment_html)
        self.assertIn('data-product-handle="the-pearl-branch-bracelet"', fragment_html)
        self.assertIn('data-product-handle="the-paprika-necklace-duo"', fragment_html)
        self.assertIn('data-product-handle="the-netted-stone-pendant"', fragment_html)

    def test_store_js_lazy_loads_cart_page_upsells(self):
        source = self.store_js_source()
        binding_source = source[
            source.index("function bindDeferredCartPageUpsells()"):
            source.index("function hydrateVisibleProductDetailImages()")
        ]

        self.assertIn("function bindDeferredCartPageUpsells()", source)
        self.assertIn("[data-cart-page-upsell-fragment]", source)
        self.assertIn("fetch(sentinel.dataset.fragmentUrl)", source)
        self.assertIn("loadDeferredMonoFont();", source)
        self.assertIn("bindDeferredCartPageUpsells();", source)
        self.assertNotIn("IntersectionObserver", binding_source)
        self.assertNotIn("rootMargin", binding_source)
        self.assertIn('window.addEventListener("scroll", () => loadDeferredCartPageUpsells(sentinel), { passive: true, once: true });', binding_source)
        self.assertIn('window.addEventListener("pointerdown", () => loadDeferredCartPageUpsells(sentinel), { passive: true, once: true });', binding_source)

    def test_cart_page_mobile_summary_spacing_matches_live_checkout_width(self):
        source = self.store_css_source()

        self.assertIn(".cart-page__summary", source)
        self.assertIn("padding: 14px;", source)

    def test_cart_items_reserve_single_bundle_height_before_javascript_for_cls(self):
        source = self.store_css_source()

        self.assertIn(".cart-page__items", source)
        self.assertIn("min-height: 497px;", source)

    def test_cart_items_reserve_is_in_initial_html_before_async_css_for_cls(self):
        response = self.client.get("/store/cart")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('<div class="cart-page__items" data-cart-lines style="min-height: 497px"></div>', html)

    def test_cart_empty_state_keeps_centered_live_treatment(self):
        source = self.store_css_source()

        self.assertIn(".empty-state", source)
        self.assertIn("place-items: center", source)
        self.assertIn("text-align: center", source)
        self.assertIn(".cart-page__empty", source)

    def test_cart_css_matches_live_mobile_item_and_page_spacing(self):
        source = self.store_css_source()

        self.assertIn(".cart {\n      padding: 79px 0 0;", source)
        self.assertIn(".cart-page {\n      display: block;\n      padding: 0 10px;", source)
        self.assertIn("min-height: 266px;", source)
        self.assertIn("margin: 20px 0;", source)
        self.assertIn(".cart-page__summary {\n      background: #fff;\n      border: 1px solid #e6e6e6;\n      border-radius: 5px;\n      box-sizing: border-box;\n      margin-top: -1px;\n      min-height: 271px;", source)
        self.assertIn("height: 271px;", source)
        self.assertIn(".cart-page__gift-message__wrap {\n      align-items: flex-start;\n      background: #fff;\n      border: 1px solid #e6e6e6;\n      border-radius: 5px;\n      box-sizing: border-box;\n      display: flex;\n      flex-wrap: wrap;\n      height: 78px;", source)
        self.assertIn(".cart-page__shipping {\n      color: #000;\n      font-size: .875rem;\n      line-height: 135%;\n      margin: 14px 0 0;\n      white-space: nowrap;", source)
        self.assertIn(".cart-page__summary-title {\n      font-size: .875rem;\n      font-weight: 700;\n      line-height: 135%;\n      margin: 0 0 22px;", source)
        self.assertIn(".cart-upsell {\n      box-sizing: border-box;\n      height: 493px;\n      margin: 0;", source)
        self.assertIn(".cart-upsell__title {\n      align-content: center;\n      align-items: center;\n      display: flex;\n      flex-wrap: wrap;\n      height: 114px;", source)
        self.assertIn(".cart-upsell .product-tile {\n      height: 379px;\n      width: 267px;", source)

    def test_cart_css_matches_live_desktop_single_item_geometry(self):
        source = self.store_css_source()

        self.assertIn(".cart {\n        box-sizing: border-box;\n        min-height: 1016px;\n        padding: 63px 0 10px;", source)
        self.assertIn(".cart-page {\n        display: flex;\n        padding: 0 10px;\n        position: static;", source)
        self.assertIn(".cart-page__items {\n        width: 846px;", source)
        self.assertIn(".cart-page__item {\n        background: transparent;\n        display: flex;\n        margin: -1px 0 0;\n        min-height: 292px;\n        padding: 0;\n        width: 846px;", source)
        self.assertIn(".cart-page__gift-message__wrap {\n        margin: -1px 0 0;\n        min-height: 58px;\n        width: calc(100vw - 20px);", source)
        self.assertIn(".cart-page__gift-message__wrap label {\n        line-height: 56px;", source)
        self.assertIn(".cart-page__summary {\n        border: 0;\n        margin: 147px 55px 0 auto;\n        padding: 0;\n        position: static;", source)
        self.assertIn(".cart-page__checkout {\n        display: block;\n        margin: 20px 0;\n        padding: 0;\n        width: 305px;", source)
        self.assertIn(".cart-upsell {\n        display: none;", source)

    def test_cart_drawer_uses_live_checkout_and_item_classes(self):
        response = self.client.get("/store")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("cart-drawer__content js-cartContent", html)
        self.assertIn("data-cart-drawer-title", html)
        self.assertIn("cart-drawer__items__container", html)
        self.assertIn('<a class="cart-drawer__checkout button button--blue" href="/store/cart">Checkout</a>', html)
        self.assertNotIn("cart-drawer__view-cart", html)

    def test_cart_drawer_renders_live_upsell_carousel_shell(self):
        response = self.client.get("/store")
        fragment_response = self.client.get("/store/cart-drawer-upsells-fragment")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(fragment_response.status_code, 200)
        html = response.get_data(as_text=True)
        fragment_html = fragment_response.get_data(as_text=True)
        self.assertIn("data-cart-drawer-upsell-fragment", html)
        self.assertIn('/store/cart-drawer-upsells-fragment', html)
        self.assertNotIn("cart-drawer__upsell slick-slider", html)
        self.assertNotIn("A few more ideas...", html)
        self.assertNotIn('data-store-add data-handle="the-salt-pepper-cylinder-bracelet-stack"', html)
        self.assertIn("cart-drawer__upsell slick-slider", fragment_html)
        self.assertIn("A few more ideas...", fragment_html)
        self.assertIn("swiper-upsell-prev", fragment_html)
        self.assertIn("swiper-upsell-next", fragment_html)
        self.assertIn("cart-drawer__upsell-track", fragment_html)
        self.assertIn('data-store-add data-handle="the-salt-pepper-cylinder-bracelet-stack"', fragment_html)

    def test_cart_drawer_upsell_images_are_deferred_until_drawer_opens(self):
        response = self.client.get("/store/cart-drawer-upsells-fragment")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        upsell_start = html.index('<div class="cart-drawer__upsell slick-slider"')
        upsell_html = html[upsell_start:]
        first_image_start = upsell_html.index("<img")
        first_image_end = upsell_html.index(">", first_image_start)
        first_image_tag = upsell_html[first_image_start:first_image_end]

        self.assertIn("data-cart-deferred-image", first_image_tag)
        self.assertIn("data-src=", first_image_tag)
        self.assertIn("data-srcset=", first_image_tag)
        self.assertIn('sizes="120px"', first_image_tag)
        self.assertNotIn(" src=", first_image_tag)
        self.assertNotIn(" srcset=", first_image_tag)

    def test_store_js_lazy_loads_cart_drawer_upsells(self):
        source = self.store_js_source()

        self.assertIn("async function loadCartDrawerUpsells()", source)
        self.assertIn("[data-cart-drawer-upsell-fragment]", source)
        self.assertIn("fetch(target.dataset.fragmentUrl)", source)
        self.assertIn("await loadCartDrawerUpsells();", source)

    def test_cart_drawer_hydrates_deferred_upsell_images_when_opened(self):
        source = (pocket.BASE_DIR / "pages" / "store" / "store.js").read_text(encoding="utf-8")
        open_drawer_source = source[
            source.index("async function openCartDrawer()"):
            source.index("function openCollectionDrawer")
        ]

        self.assertIn("function hydrateCartDrawerImages()", source)
        self.assertIn('[data-cart-drawer] [data-cart-deferred-image][data-src]', source)
        self.assertIn("hydrateCartDrawerImages();", open_drawer_source)
        self.assertLess(
            open_drawer_source.index("hydrateCartDrawerImages();"),
            open_drawer_source.index('drawer.setAttribute("aria-hidden", "false")'),
        )

    def test_cart_javascript_renders_live_line_item_classes(self):
        source = (pocket.BASE_DIR / "pages" / "store" / "store.js").read_text(encoding="utf-8")

        self.assertIn("cart-drawer__item", source)
        self.assertIn("cart-drawer__item__image", source)
        self.assertIn("cart-drawer__item__details", source)
        self.assertIn("cart-drawer__item__options", source)
        self.assertIn("cart-drawer__item__price", source)
        self.assertIn("cart-page__item", source)
        self.assertIn("cart-page__checkout", source)
        self.assertIn("quantity: ${item.qty}", source)
        self.assertNotIn("cart-drawer__quantity", source)

    def test_cart_page_item_options_do_not_duplicate_unit_price(self):
        source = (pocket.BASE_DIR / "pages" / "store" / "store.js").read_text(encoding="utf-8")

        self.assertNotIn('cart-page__item__options">${escapeHtml(meta.variant.title)}<br>${price(meta.variant.price)}', source)

    def test_cart_javascript_renders_live_bundle_includes(self):
        source = (pocket.BASE_DIR / "pages" / "store" / "store.js").read_text(encoding="utf-8")

        self.assertIn("isBundleVariant", source)
        self.assertIn("isBundleStyleLine", source)
        self.assertIn("bundleIncludes", source)
        self.assertIn("cart-page__item--bundle", source)
        self.assertIn("cart-drawer__item--bundle", source)
        self.assertIn("includes:", source)
        self.assertIn("cartPageQuantityHtml(item, meta)", source)

    def test_cart_javascript_renders_set_child_variants_like_live_bundle_lines(self):
        source = (pocket.BASE_DIR / "pages" / "store" / "store.js").read_text(encoding="utf-8")

        self.assertIn("function isSetProduct(product)", source)
        self.assertIn("function isBundleStyleLine(product, variant)", source)
        self.assertIn("if (isBundleStyleLine(meta.product, meta.variant)) return \"\";", source)
        self.assertIn("bundleIncludeItems(meta.product, meta.variant)", source)
        self.assertIn("cart-page__item__image-mobile cart-page__item__image-mobile--top", source)
        self.assertIn("bundle-options-label", source)
        self.assertIn("bundle-child first", source)

    def test_cart_drawer_uses_bundle_style_logic_for_set_child_variants(self):
        source = (pocket.BASE_DIR / "pages" / "store" / "store.js").read_text(encoding="utf-8")

        self.assertIn("const drawerBundleClass = isBundleStyleLine(meta.product, meta.variant) ? \" cart-drawer__item--bundle\" : \"\";", source)
        self.assertIn("drawerOptionsHtml(meta, item)", source)
        self.assertIn("${includes.map(title => `<li>${escapeHtml(title)}</li>`).join(\"\")}", source)
        self.assertIn("<li>quantity: ${item.qty}</li>", source)

    def test_cart_drawer_css_keeps_live_checkout_visible_on_desktop(self):
        source = self.store_css_source()

        self.assertIn(".cart-drawer__header {\n      min-height: 55px;", source)
        self.assertIn("height: 55px;\n      padding: 17px 23px;", source)
        self.assertIn(".cart-drawer__items {\n      flex: 0 0 auto;\n      height: 219px;\n      max-height: 219px;", source)
        self.assertIn("overflow: hidden;\n      padding: 0 23px;", source)
        self.assertIn(".cart-drawer__item--bundle {\n      min-height: 160px;", source)
        self.assertIn(".cart-drawer__upsell {\n      background: #fff;\n      border: 1px solid #e6e6e6;\n      border-radius: 5px;\n      box-sizing: border-box;\n      height: 298px;", source)
        self.assertIn(".cart-drawer__summary {\n      display: grid;\n      gap: 8px;\n      height: 112px;", source)
        self.assertIn(".cart-drawer__checkout {\n      height: 52px;\n      line-height: 52px;\n      min-height: 52px;", source)

    def test_cart_css_matches_live_mobile_line_item_internals(self):
        source = self.store_css_source()

        self.assertIn(".cart-page__item__copy {\n      display: flex;\n      flex-direction: column;\n      min-height: 235px;\n      padding-left: 0;", source)
        self.assertIn(".cart-page__item__details {\n      display: flex;\n      font-size: 1.125rem;\n      font-weight: 600;\n      justify-content: space-between;\n      line-height: 145%;\n      min-height: 101px;\n      padding-left: 101px;", source)
        self.assertIn(".cart-page__item__image-mobile {\n      border: 1px solid #e6e6e6;\n      border-radius: 5px;\n      box-sizing: border-box;\n      height: 101px;\n      left: -15px;", source)
        self.assertIn(".cart-page__item__line-price {\n      flex: 0 0 79px;", source)
        self.assertIn(".cart-page__item__remove {\n      background: transparent;\n      border: 0;\n      color: #000;\n      cursor: pointer;\n      font-size: .875rem;\n      height: 47px;\n      padding: 0;\n      position: absolute;\n      right: 14px;\n      top: 86px;\n      width: 91px;", source)
        self.assertIn(".cart-page__item--bundle-single {\n      min-height: 265px;", source)

    def test_cart_javascript_renders_live_gift_message_option(self):
        source = (pocket.BASE_DIR / "pages" / "store" / "store.js").read_text(encoding="utf-8")

        self.assertIn("cart-page__gift-message__wrap", source)
        self.assertIn("cart-page__gift-toggle", source)
        self.assertIn("cart-page__gift-message", source)
        self.assertIn("js-cartGiftMessage", source)
        self.assertIn("maxlength=\"100\"", source)
        self.assertIn("this is a gift", source)
        self.assertIn("toggleGiftMessage", source)

    def test_cart_javascript_forces_drawer_visible_inline_when_opened(self):
        source = (pocket.BASE_DIR / "pages" / "store" / "store.js").read_text(encoding="utf-8")

        self.assertIn("setCartDrawerVisibility", source)
        self.assertIn("function cartDrawerOpenRight()", source)
        self.assertIn('drawer.classList.toggle("is-open", visible)', source)
        self.assertIn('drawer.style.setProperty("right", cartDrawerOpenRight(), "important")', source)
        self.assertIn('drawer.style.setProperty("transform", "none", "important")', source)
        self.assertIn('drawer.style.setProperty("visibility", "visible", "important")', source)

    def test_cart_open_state_has_body_scoped_transform_override(self):
        source = self.store_css_source()

        self.assertIn(".cart-drawer.is-open", source)
        self.assertIn('.drawer-is-open .cart-drawer[aria-hidden="false"]', source)
        self.assertIn("right: 10px !important", source)
        self.assertIn("transform: none !important", source)
        self.assertIn("right: 8px !important", source)

    def test_cart_css_supports_live_bundle_line_heights(self):
        source = self.store_css_source()

        self.assertIn(".cart-page__item--bundle {\n      min-height: 399px;", source)
        self.assertIn(".cart-drawer__item--bundle {\n      min-height: 160px;", source)

    def test_store_javascript_toggles_search_and_collection_overlay(self):
        source = (pocket.BASE_DIR / "pages" / "store" / "store.js").read_text(encoding="utf-8")

        self.assertIn("openSearchDrawer", source)
        self.assertIn("data-search-open", source)
        self.assertIn("data-search-close", source)
        self.assertIn("data-filter-overlay", source)
        self.assertIn("setCollectionOverlay", source)
        self.assertIn("data-shipping-promo-close", source)

    def test_collection_javascript_sets_drawer_inline_visibility(self):
        source = (pocket.BASE_DIR / "pages" / "store" / "store.js").read_text(encoding="utf-8")

        self.assertIn("setCollectionDrawerVisibility", source)
        self.assertIn('drawer.style.setProperty("transform", "translateY(0)", "important")', source)
        self.assertIn('drawer.style.setProperty("visibility", "visible", "important")', source)

    def test_collection_filter_drawer_uses_live_mobile_bottom_sheet_motion(self):
        source = self.store_css_source()

        self.assertIn(".collection-filter__drawer", source)
        self.assertIn("bottom: 0", source)
        self.assertIn("transform: translateY(100%)", source)
        self.assertIn('.collection-filter__drawer[aria-hidden="false"]', source)

    def test_collection_filter_open_state_has_body_scoped_override(self):
        source = self.store_css_source()

        self.assertIn('.collection-filter-is-open .collection-filter__drawer[aria-hidden="false"]', source)
        self.assertIn("transform: translateY(0) !important", source)

    def test_collection_desktop_filter_drawer_uses_live_panel_width(self):
        source = self.store_css_source()

        self.assertIn(".collection-filter__drawer {\n        border-radius: 5px;\n        bottom: auto;\n        left: auto;\n        max-width: 390px;\n        right: 8px;\n        top: 72px;\n        width: 390px;", source)
        self.assertIn(".collection-filter__drawer__head svg {\n        height: 15px;\n        width: 15px;", source)

    def test_store_base_uses_versioned_store_script_for_fresh_behavior(self):
        response = self.client.get("/store")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('<script src="/store/assets/store.min.js?v=20260605-cart-a11y" defer fetchpriority="low"></script>', html)

    def test_footer_logo_is_deferred_until_scroll_for_lighthouse(self):
        response = self.client.get("/store/products/the-cylinder-cord-necklace-cloud-blue")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        logo_start = html.index('<div class="footer__logo">')
        image_start = html.index("<img", logo_start)
        image_end = html.index(">", image_start)
        image_tag = html[image_start:image_end]

        self.assertIn("data-footer-deferred-image", image_tag)
        self.assertIn("data-src=", image_tag)
        self.assertIn("data-srcset=", image_tag)
        self.assertIn("data-sizes=", image_tag)
        self.assertNotIn(" src=", image_tag)
        self.assertNotIn(" srcset=", image_tag)

    def test_store_js_hydrates_deferred_footer_logo_after_user_motion(self):
        source = (pocket.BASE_DIR / "pages" / "store" / "store.js").read_text(encoding="utf-8")

        self.assertIn("function bindDeferredFooterImageHydration()", source)
        self.assertIn("[data-footer-deferred-image][data-src]", source)
        self.assertIn("hydrateDeferredImage(image);", source)
        self.assertIn('window.addEventListener("scroll", scheduleHydration', source)
        self.assertIn("bindDeferredFooterImageHydration();", source)

    def test_cart_bundle_include_thumbnails_use_compact_lazy_images(self):
        source = (pocket.BASE_DIR / "pages" / "store" / "store.js").read_text(encoding="utf-8")

        self.assertIn("image: productImage(product, child, 64)", source)
        self.assertIn('<img loading="lazy" decoding="async" src="${item.image}" alt="">', source)

    def test_empty_cart_renderers_do_not_fetch_catalog_before_empty_state(self):
        source = (pocket.BASE_DIR / "pages" / "store" / "store.js").read_text(encoding="utf-8")
        drawer_source = source[
            source.index("async function renderCartDrawer()"):
            source.index("function toggleGiftMessage")
        ]

        self.assertIn("const rawCart = loadCart().filter(item => Number(item.qty || 0) > 0);", drawer_source)
        self.assertIn("if (!rawCart.length) {", drawer_source)
        self.assertLess(
            drawer_source.index("if (!rawCart.length) {"),
            drawer_source.index("await loadCartCatalog(rawCart);"),
        )

    def test_store_js_reuses_inflight_catalog_request_for_cart_startup(self):
        source = (pocket.BASE_DIR / "pages" / "store" / "store.js").read_text(encoding="utf-8")

        self.assertIn("let catalogPromise = null;", source)
        self.assertIn("if (catalogPromise) return catalogPromise;", source)
        self.assertIn("catalogPromise = fetch(\"/store/catalog.json\")", source)
        self.assertIn("catalogPromise = null;", source)

    def test_store_js_defers_hidden_cart_drawer_render_until_open(self):
        source = (pocket.BASE_DIR / "pages" / "store" / "store.js").read_text(encoding="utf-8")
        startup_source = source[source.rindex("updateCount();"):]
        open_drawer_source = source[
            source.index("async function openCartDrawer()"):
            source.index("function setCollectionDrawerVisibility")
        ]
        cart_page_source = source[
            source.index("async function renderCartPage()"):
            source.index("async function renderCartDrawer()")
        ]

        self.assertIn("updateCount();", startup_source)
        self.assertNotIn("renderCartDrawer();", startup_source)
        self.assertIn("await renderCartDrawer();", open_drawer_source)
        self.assertIn("saveCart(cart, { renderDrawer: false });", cart_page_source)

    def test_cart_renderers_use_compact_cart_catalog_loader(self):
        source = (pocket.BASE_DIR / "pages" / "store" / "store.js").read_text(encoding="utf-8")
        cart_page_source = source[
            source.index("async function renderCartPage()"):
            source.index("async function renderCartDrawer()")
        ]
        cart_drawer_source = source[
            source.index("async function renderCartDrawer()"):
            source.index("function toggleGiftMessage")
        ]

        self.assertIn("async function loadCartCatalog(cart = [])", source)
        self.assertIn("function cartCatalogUrl(cart)", source)
        self.assertIn('return `/store/cart-items.json?ids=${ids.join(",")}`;', source)
        self.assertIn('return "/store/cart-index.json";', source)
        self.assertIn("await loadCartCatalog(rawCart);", cart_page_source)
        self.assertIn("await loadCartCatalog(rawCart);", cart_drawer_source)
        self.assertNotIn("await loadCatalog();", cart_page_source)
        self.assertNotIn("await loadCatalog();", cart_drawer_source)

    def test_store_assets_are_cacheable_for_lighthouse(self):
        response = self.client.get("/store/assets/store.min.js?v=20260605-js-min")
        self.addCleanup(response.close)

        self.assertEqual(response.status_code, 200)
        script = response.get_data(as_text=True)
        self.assertIn("public", response.headers.get("Cache-Control", ""))
        self.assertIn("max-age=31536000", response.headers.get("Cache-Control", ""))
        self.assertIn("function loadDeferredMonoFont()", script)
        self.assertIn("function cartCatalogUrl(cart)", script)
        self.assertLess(len(script), len(self.store_js_source()))

    def test_store_js_runtime_images_request_small_shopify_widths(self):
        source = (pocket.BASE_DIR / "pages" / "store" / "store.js").read_text(encoding="utf-8")

        self.assertIn("function shopifyImageUrl(src, width)", source)
        self.assertIn("productImage(meta.product, meta.variant, 180)", source)
        self.assertIn("productImage(product, selectedVariant, 480)", source)

    def test_unknown_product_returns_404(self):
        response = self.client.get("/store/products/nope")

        self.assertEqual(response.status_code, 404)

    def test_store_catalog_is_public_json(self):
        response = self.client.get("/store/catalog.json")
        self.addCleanup(response.close)

        self.assertEqual(response.status_code, 200)
        self.assertIn("products", response.get_json())

    def test_cart_index_is_compact_variant_json(self):
        catalog_response = self.client.get("/store/catalog.json")
        cart_response = self.client.get("/store/cart-index.json")
        self.addCleanup(catalog_response.close)
        self.addCleanup(cart_response.close)

        self.assertEqual(cart_response.status_code, 200)
        self.assertIn("public", cart_response.headers.get("Cache-Control", ""))
        self.assertIn("max-age=3600", cart_response.headers.get("Cache-Control", ""))

        catalog_bytes = catalog_response.get_data()
        cart_bytes = cart_response.get_data()
        self.assertLess(len(cart_bytes), len(catalog_bytes) * 0.4)

        data = cart_response.get_json()
        product = data["products"][0]
        variant = product["variants"][0]
        self.assertIn("title", product)
        self.assertIn("handle", product)
        self.assertIn("images", product)
        self.assertNotIn("id", product)
        self.assertIn("id", variant)
        self.assertIn("title", variant)
        self.assertIn("price", variant)
        self.assertIn("position", variant)
        self.assertNotIn("available", variant)
        self.assertFalse(any(
            "featured_image" in item and item["featured_image"] is None
            for product_item in data["products"]
            for item in product_item["variants"]
        ))
        self.assertNotIn("body_html", product)
        self.assertNotIn("tags", product)

    def test_cart_items_json_returns_only_requested_variant_products(self):
        first_product, first_variant = self.first_available_variant()
        response = self.client.get(f"/store/cart-items.json?ids={first_variant['id']}")
        full_response = self.client.get("/store/cart-index.json")
        self.addCleanup(response.close)
        self.addCleanup(full_response.close)

        self.assertEqual(response.status_code, 200)
        self.assertIn("public", response.headers.get("Cache-Control", ""))
        self.assertIn("max-age=3600", response.headers.get("Cache-Control", ""))
        self.assertLess(len(response.get_data()), len(full_response.get_data()) * 0.25)

        data = response.get_json()
        self.assertEqual(len(data["products"]), 1)
        product = data["products"][0]
        self.assertEqual(product["handle"], first_product["handle"])
        self.assertIn(int(first_variant["id"]), {int(variant["id"]) for variant in product["variants"]})
        self.assertNotIn("body_html", product)
        self.assertNotIn("tags", product)

    def test_mock_checkout_verifies_cart_against_catalog(self):
        _product, variant = self.first_available_variant()
        variant_id = int(variant["id"])
        quantity = 2

        response = self.client.post(
            "/store/api/checkout",
            json={"cartItems": [{"id": variant_id, "qty": quantity}]},
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        expected_subtotal = pocket.parse_price_cents(variant["price"]) * quantity
        self.assertEqual(data["mode"], "mock")
        self.assertEqual(data["item_count"], quantity)
        self.assertEqual(data["subtotal_cents"], expected_subtotal)
        self.assertIn(f"/cart/{variant_id}:{quantity}", data["shopify_cart_url"])

    def test_mock_checkout_rejects_unknown_variant(self):
        response = self.client.post(
            "/store/api/checkout",
            json={"cartItems": [{"id": 999999999999999, "qty": 1}]},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Unknown variant id", response.get_json()["error"])


if __name__ == "__main__":
    unittest.main()
