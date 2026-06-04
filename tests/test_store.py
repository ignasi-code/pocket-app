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

    def test_homepage_product_module_title_uses_live_regular_weight(self):
        source = (pocket.BASE_DIR / "templates" / "store" / "base.html").read_text(encoding="utf-8")

        self.assertIn(".product-module__title", source)
        self.assertIn("font-weight: 400", source)

    def test_homepage_split_banner_uses_live_mobile_cta_treatment(self):
        source = (pocket.BASE_DIR / "templates" / "store" / "base.html").read_text(encoding="utf-8")

        self.assertIn(".double-image-banner__tile a", source)
        self.assertIn("bottom: 5%", source)
        self.assertIn("font-size: 1rem", source)
        self.assertIn(".double-image-banner__tile__cta--black", source)
        self.assertNotIn(".split-tile::before", source)

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
        self.assertIn(product["title"], html)
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

    def test_store_uses_live_theme_product_tile_structure(self):
        response = self.client.get("/store/collections/the-summer-capsule")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("product-tile", html)
        self.assertIn("product-tile__image", html)
        self.assertIn("product-tile__image__hover", html)
        self.assertIn("product-tile__title", html)
        self.assertIn("product-tile__add", html)

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

    def test_collection_filter_drawer_uses_live_inner_structure(self):
        response = self.client.get("/store/collections/necklaces")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("collection-filter__drawer__head", html)
        self.assertIn("collection-filter__drawer__scroll", html)
        self.assertIn("collection-filter__options", html)
        self.assertIn("collection-filter__option", html)
        self.assertIn("collection-filter__checkbox", html)
        self.assertIn("collection-filter__buttons", html)
        self.assertIn(">Apply<", html)

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
        first = html.index('data-product-handle="the-salt-pepper-cylinder-necklace-set"')
        second = html.index('data-product-handle="the-cylinder-cord-necklace-lemon-yellow"')
        self.assertLess(first, second)

    def test_collection_price_sort_reorders_products(self):
        response = self.client.get("/store/collections/necklaces?sort_by=price-ascending")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        cheapest = html.index('data-product-handle="the-happy-cord-charm-necklace-blood-orange-red"')
        curated = html.index('data-product-handle="the-salt-pepper-cylinder-necklace-set"')
        self.assertLess(cheapest, curated)

    def test_collection_color_filter_filters_products_and_preserves_checked_state(self):
        response = self.client.get("/store/collections/necklaces?filter.p.m.roxanne-assoulin.filter_color%5B%5D=yellow")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('data-results-count="2"', html)
        self.assertIn('data-product-handle="the-salt-pepper-cylinder-necklace-set"', html)
        self.assertIn('data-product-handle="the-cylinder-cord-necklace-lemon-yellow"', html)
        self.assertNotIn('data-product-handle="the-cylinder-cord-necklace-cloud-blue"', html)
        self.assertIn('name="filter.p.m.roxanne-assoulin.filter_color[]" value="yellow" checked', html)
        self.assertNotIn("pagination__next", html)

    def test_collection_category_filter_filters_custom_collection_and_preserves_checked_state(self):
        response = self.client.get("/store/collections/custom?filter.p.product_type%5B%5D=Bracelets")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('data-product-handle="the-cylinder-cord-bracelet-lemon-yellow"', html)
        self.assertNotIn('data-product-handle="the-cylinder-cord-necklace-lemon-yellow"', html)
        self.assertIn('name="filter.p.product_type[]" value="Bracelets" checked', html)
        self.assertIn("type=\"submit\"", html)

    def test_shop_collection_search_query_filters_products_and_preserves_input(self):
        response = self.client.get("/store/collections/shop?q=paprika")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('data-results-count="3"', html)
        self.assertIn('value="paprika"', html)
        self.assertIn('data-product-handle="the-paprika-necklace-duo"', html)
        self.assertIn('data-product-handle="the-paprika-bracelet-duo"', html)
        self.assertNotIn('data-product-handle="the-salt-pepper-cylinder-necklace-set"', html)
        self.assertNotIn("pagination__next", html)

    def test_collection_sort_links_preserve_search_and_filter_state(self):
        response = self.client.get(
            "/store/collections/necklaces?q=lemon&filter.p.m.roxanne-assoulin.filter_color%5B%5D=yellow"
        )

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn(
            'href="?q=lemon&amp;filter.p.m.roxanne-assoulin.filter_color%5B%5D=yellow&amp;sort_by=price-ascending"',
            html,
        )
        self.assertIn(
            'href="?q=lemon&amp;filter.p.m.roxanne-assoulin.filter_color%5B%5D=yellow&amp;sort_by=price-descending"',
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
        self.assertIn('class="cart-page__checkout"', html)
        self.assertNotIn("cart-page__gift", html)

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

    def test_cart_drawer_uses_live_checkout_and_item_classes(self):
        response = self.client.get("/store")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("cart-drawer__content js-cartContent", html)
        self.assertIn("data-cart-drawer-title", html)
        self.assertIn("cart-drawer__items__container", html)
        self.assertIn("cart-drawer__checkout button button--blue", html)
        self.assertIn("cart-drawer__view-cart button", html)

    def test_cart_javascript_renders_live_line_item_classes(self):
        source = (pocket.BASE_DIR / "pages" / "store" / "store.js").read_text(encoding="utf-8")

        self.assertIn("cart-drawer__item", source)
        self.assertIn("cart-drawer__item__image", source)
        self.assertIn("cart-drawer__item__details", source)
        self.assertIn("cart-drawer__item__options", source)
        self.assertIn("cart-drawer__item__price", source)
        self.assertIn("cart-page__item", source)
        self.assertIn("cart-page__checkout", source)

    def test_cart_page_item_options_do_not_duplicate_unit_price(self):
        source = (pocket.BASE_DIR / "pages" / "store" / "store.js").read_text(encoding="utf-8")

        self.assertNotIn('cart-page__item__options">${escapeHtml(meta.variant.title)}<br>${price(meta.variant.price)}', source)

    def test_cart_javascript_renders_live_bundle_includes(self):
        source = (pocket.BASE_DIR / "pages" / "store" / "store.js").read_text(encoding="utf-8")

        self.assertIn("isBundleVariant", source)
        self.assertIn("bundleIncludes", source)
        self.assertIn("cart-page__item--bundle", source)
        self.assertIn("cart-drawer__item--bundle", source)
        self.assertIn("Includes:", source)
        self.assertIn("cartPageQuantityHtml(item, meta)", source)

    def test_cart_javascript_renders_live_gift_option_without_old_layout_class(self):
        source = (pocket.BASE_DIR / "pages" / "store" / "store.js").read_text(encoding="utf-8")

        self.assertIn("cart-gift-option", source)
        self.assertIn("this is a gift", source)
        self.assertNotIn("cart-page__gift", source)

    def test_cart_css_supports_live_bundle_line_heights(self):
        source = (pocket.BASE_DIR / "templates" / "store" / "base.html").read_text(encoding="utf-8")

        self.assertIn(".cart-page__item--bundle", source)
        self.assertIn("min-height: 399px", source)
        self.assertIn(".cart-drawer__item--bundle", source)
        self.assertIn("min-height: 204px", source)

    def test_store_javascript_toggles_search_and_collection_overlay(self):
        source = (pocket.BASE_DIR / "pages" / "store" / "store.js").read_text(encoding="utf-8")

        self.assertIn("openSearchDrawer", source)
        self.assertIn("data-search-open", source)
        self.assertIn("data-search-close", source)
        self.assertIn("data-filter-overlay", source)
        self.assertIn("setCollectionOverlay", source)

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
        self.assertIn("/store/assets/store.js?v=", html)

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
