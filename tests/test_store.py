import html as html_lib
import unittest

import app as pocket


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.client = pocket.app.test_client()

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
        self.assertIn("data-store-add", html)
        self.assertIn("/store/cart", html)

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

    def test_product_page_keeps_shipping_promo_out_of_pdp_first_view(self):
        response = self.client.get("/store/products/the-cylinder-cord-necklace-cloud-blue")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertNotIn("shipping-promo js-shippingPromo", html)

    def test_shipping_promo_css_matches_live_mobile_bar(self):
        source = (pocket.BASE_DIR / "templates" / "store" / "base.html").read_text(encoding="utf-8")

        self.assertIn(".shipping-promo {\n      background: #cf3d2f;", source)
        self.assertIn("position: fixed;\n      right: 10px;\n      top: 79px;", source)
        self.assertIn(".shipping-promo.is-hidden {\n      display: none;", source)

    def test_homepage_product_module_title_uses_live_regular_weight(self):
        source = (pocket.BASE_DIR / "templates" / "store" / "base.html").read_text(encoding="utf-8")

        self.assertIn(".product-module__title", source)
        self.assertIn("font-weight: 400", source)

    def test_homepage_desktop_category_module_matches_live_height(self):
        source = (pocket.BASE_DIR / "templates" / "store" / "base.html").read_text(encoding="utf-8")

        self.assertIn(".category-module {\n        height: 460px;\n        padding: 0;", source)
        self.assertIn(".category-module__text {\n        font-size: 3rem;\n        line-height: 1.2;", source)
        self.assertIn("max-width: 850px;\n        padding-bottom: 177px;", source)
        self.assertIn(".category-module__text--pink::after {\n        border-bottom: 2px solid #000;\n        top: 57px;", source)

    def test_homepage_split_banner_uses_live_mobile_cta_treatment(self):
        source = (pocket.BASE_DIR / "templates" / "store" / "base.html").read_text(encoding="utf-8")

        self.assertIn(".double-image-banner__tile a", source)
        self.assertIn("bottom: 5%", source)
        self.assertIn("font-size: 1rem", source)
        self.assertIn("left: 50%", source)
        self.assertIn("transform: translate3d(-57%, -50%, 0)", source)
        self.assertIn(".double-image-banner__tile__cta--black", source)
        self.assertNotIn(".split-tile::before", source)
        self.assertNotIn("font-size: 9.375rem", source)

    def test_homepage_desktop_product_module_matches_live_spacing(self):
        source = (pocket.BASE_DIR / "templates" / "store" / "base.html").read_text(encoding="utf-8")

        self.assertIn(".product-module__title {\n        font-size: 3rem;\n        line-height: 1.2;", source)
        self.assertIn("padding-bottom: 30px;\n        padding-left: 65px;", source)
        self.assertIn(".product-module__cta {\n        font-size: 1.125rem;\n        padding-right: 92px;", source)
        self.assertIn(".product-module__products {\n        flex-wrap: wrap;\n        padding: 0 2px 1px;", source)

    def test_homepage_desktop_product_module_matches_live_height_contract(self):
        source = (pocket.BASE_DIR / "templates" / "store" / "base.html").read_text(encoding="utf-8")

        self.assertIn(".product-module {\n        padding: 40px 0 50px;", source)
        self.assertIn("max-width: 559px;\n        padding-bottom: 30px;", source)
        self.assertIn(".product-module__cta--desktop {\n        display: block;", source)
        self.assertIn(".product-module__cta--mobile {\n        display: none;", source)

    def test_homepage_uses_live_desktop_split_assets_and_custom_category_link(self):
        response = self.client.get("/store")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("0526_Hearts_957x_crop_center", html)
        self.assertIn("0531_HappyBaby_Mobile_9f30ae56-b0cc-48f3-9f88-28ec80b99883_957x_crop_center", html)
        self.assertIn("0531_Camp_Mobile_55bf818c-5e28-4609-93ff-1e7bf5a090d6_957x_crop_center", html)
        self.assertIn("0531_ItsyBitsy_Mobile_47e7a0a7-064e-44fb-b14e-5971f5c14833_957x_crop_center", html)
        self.assertIn("href=\"/store/collections/custom\"", html)

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
        self.assertIn("data-store-add", html)

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

    def test_desktop_header_renders_live_search_login_about_cluster(self):
        response = self.client.get("/store")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        source = (pocket.BASE_DIR / "templates" / "store" / "base.html").read_text(encoding="utf-8")
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
        source = (pocket.BASE_DIR / "templates" / "store" / "base.html").read_text(encoding="utf-8")

        self.assertIn(".product-tile__copy__wrapper {\n        left: 3px;\n        right: 3px;\n        bottom: 2px;\n        grid-template-columns: minmax(0, 1fr) 76px;", source)
        self.assertIn(".product-tile__add {\n        border-radius: 0;\n        height: auto;\n        min-height: 76px;\n        width: 76px;", source)

    def test_product_tile_desktop_copy_typography_matches_live_band(self):
        source = (pocket.BASE_DIR / "templates" / "store" / "base.html").read_text(encoding="utf-8")

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
        source = (pocket.BASE_DIR / "templates" / "store" / "base.html").read_text(encoding="utf-8")

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
        source = (pocket.BASE_DIR / "templates" / "store" / "base.html").read_text(encoding="utf-8")

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
        source = (pocket.BASE_DIR / "templates" / "store" / "base.html").read_text(encoding="utf-8")

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
        source = (pocket.BASE_DIR / "templates" / "store" / "base.html").read_text(encoding="utf-8")

        self.assertIn(".collection-items {\n        display: grid;\n        grid-template-columns: repeat(4, minmax(0, 1fr));\n        padding-top: 72px;", source)
        self.assertIn("grid-column: 1 / -1;\n        height: 76px;\n        order: -1;\n        top: 72px;", source)
        self.assertIn(".collection-grid {\n        display: contents;", source)
        self.assertIn(".collection-hero {\n        grid-column: 1 / span 2;\n        grid-row: span 2;\n        height: 765px;", source)
        self.assertIn(".product-tile {\n        height: 384px;", source)

    def test_collection_desktop_filter_bar_matches_live_inset_controls(self):
        source = (pocket.BASE_DIR / "templates" / "store" / "base.html").read_text(encoding="utf-8")

        self.assertIn(".collection-filter-bar {\n        background: transparent;\n        display: flex;", source)
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

    def test_key_collection_pages_use_extracted_live_hero_assets(self):
        cases = {
            "necklaces": "Necklaces_367x374_crop_center",
            "new-arrivals": "New-Arrivals_367x374_crop_center",
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
        source = (pocket.BASE_DIR / "templates" / "store" / "base.html").read_text(encoding="utf-8")

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
        self.assertIn(".product-buy-options__add-wrapper button", html)
        self.assertIn("height: 60px", html)

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
        source = (pocket.BASE_DIR / "templates" / "store" / "base.html").read_text(encoding="utf-8")
        self.assertIn("product-details-top__image", html)
        self.assertIn("data-product-details-image", html)
        self.assertIn("CylinderCordNecklace_Cloud_1", html)
        self.assertIn(".product-details-top__image", source)

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
        source = (pocket.BASE_DIR / "templates" / "store" / "base.html").read_text(encoding="utf-8")

        self.assertIn(".product-details-bottom__col--options {\n      border-bottom: 1px solid #e6e6e6;\n      order: 1;\n      padding-bottom: 0;\n      padding-top: 0;", source)
        self.assertIn("padding: 10px 0 22px;", source)
        self.assertIn("padding: 0 0 16px;", source)

    def test_product_css_matches_live_desktop_gallery_depth(self):
        source = (pocket.BASE_DIR / "templates" / "store" / "base.html").read_text(encoding="utf-8")

        self.assertIn(".product-gallery__image__wrapper:nth-child(n+3) {\n        display: none;", source)
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
        source = (pocket.BASE_DIR / "templates" / "store" / "base.html").read_text(encoding="utf-8")
        self.assertIn('class="page product-page"', html)
        self.assertIn(".product-page {\n      padding-top: 5px;", source)

    def test_product_page_uses_live_add_to_bag_and_shipping_copy(self):
        response = self.client.get("/store/products/the-cylinder-cord-necklace-cloud-blue")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        source = (pocket.BASE_DIR / "templates" / "store" / "base.html").read_text(encoding="utf-8")
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

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("cart-upsell", html)
        self.assertIn("selected for u", html)
        self.assertIn('data-product-handle="the-salt-pepper-cylinder-bracelet-stack"', html)
        self.assertIn('data-product-handle="the-pearl-branch-bracelet"', html)
        self.assertIn('data-product-handle="the-paprika-necklace-duo"', html)
        self.assertIn('data-product-handle="the-netted-stone-pendant"', html)

    def test_cart_page_mobile_summary_spacing_matches_live_checkout_width(self):
        source = (pocket.BASE_DIR / "templates" / "store" / "base.html").read_text(encoding="utf-8")

        self.assertIn(".cart-page__summary", source)
        self.assertIn("padding: 14px;", source)

    def test_cart_css_matches_live_mobile_item_and_page_spacing(self):
        source = (pocket.BASE_DIR / "templates" / "store" / "base.html").read_text(encoding="utf-8")

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
        source = (pocket.BASE_DIR / "templates" / "store" / "base.html").read_text(encoding="utf-8")

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

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("cart-drawer__upsell slick-slider", html)
        self.assertIn("A few more ideas...", html)
        self.assertIn("swiper-upsell-prev", html)
        self.assertIn("swiper-upsell-next", html)
        self.assertIn("cart-drawer__upsell-track", html)
        self.assertIn('data-store-add data-handle="the-salt-pepper-cylinder-bracelet-stack"', html)

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
        source = (pocket.BASE_DIR / "templates" / "store" / "base.html").read_text(encoding="utf-8")

        self.assertIn(".cart-drawer__header {\n      min-height: 55px;", source)
        self.assertIn("height: 55px;\n      padding: 17px 23px;", source)
        self.assertIn(".cart-drawer__items {\n      flex: 0 0 auto;\n      height: 219px;\n      max-height: 219px;", source)
        self.assertIn("overflow: hidden;\n      padding: 0 23px;", source)
        self.assertIn(".cart-drawer__item--bundle {\n      min-height: 160px;", source)
        self.assertIn(".cart-drawer__upsell {\n      background: #fff;\n      border: 1px solid #e6e6e6;\n      border-radius: 5px;\n      box-sizing: border-box;\n      height: 298px;", source)
        self.assertIn(".cart-drawer__summary {\n      display: grid;\n      gap: 8px;\n      height: 112px;", source)
        self.assertIn(".cart-drawer__checkout {\n      height: 52px;\n      line-height: 52px;\n      min-height: 52px;", source)

    def test_cart_css_matches_live_mobile_line_item_internals(self):
        source = (pocket.BASE_DIR / "templates" / "store" / "base.html").read_text(encoding="utf-8")

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
        source = (pocket.BASE_DIR / "templates" / "store" / "base.html").read_text(encoding="utf-8")

        self.assertIn(".cart-drawer.is-open", source)
        self.assertIn('.drawer-is-open .cart-drawer[aria-hidden="false"]', source)
        self.assertIn("right: 10px !important", source)
        self.assertIn("transform: none !important", source)
        self.assertIn("right: 8px !important", source)

    def test_cart_css_supports_live_bundle_line_heights(self):
        source = (pocket.BASE_DIR / "templates" / "store" / "base.html").read_text(encoding="utf-8")

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
        source = (pocket.BASE_DIR / "templates" / "store" / "base.html").read_text(encoding="utf-8")

        self.assertIn(".collection-filter__drawer", source)
        self.assertIn("bottom: 0", source)
        self.assertIn("transform: translateY(100%)", source)
        self.assertIn('.collection-filter__drawer[aria-hidden="false"]', source)

    def test_collection_filter_open_state_has_body_scoped_override(self):
        source = (pocket.BASE_DIR / "templates" / "store" / "base.html").read_text(encoding="utf-8")

        self.assertIn('.collection-filter-is-open .collection-filter__drawer[aria-hidden="false"]', source)
        self.assertIn("transform: translateY(0) !important", source)

    def test_store_base_uses_versioned_store_script_for_fresh_behavior(self):
        response = self.client.get("/store")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("/store/assets/store.js?v=20260604-home-collection", html)

    def test_unknown_product_returns_404(self):
        response = self.client.get("/store/products/nope")

        self.assertEqual(response.status_code, 404)

    def test_store_catalog_is_public_json(self):
        response = self.client.get("/store/catalog.json")
        self.addCleanup(response.close)

        self.assertEqual(response.status_code, 200)
        self.assertIn("products", response.get_json())

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
