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

    def test_store_uses_live_theme_product_tile_structure(self):
        response = self.client.get("/store/collections/the-summer-capsule")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("product-tile", html)
        self.assertIn("product-tile__image", html)
        self.assertIn("product-tile__image__hover", html)
        self.assertIn("product-tile__title", html)
        self.assertIn("product-tile__add", html)

    def test_collection_page_exposes_filter_and_sort_drawers(self):
        response = self.client.get("/store/collections/the-summer-capsule")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("collection-filter__bar", html)
        self.assertIn("collection-filter__drawer--filter", html)
        self.assertIn("collection-filter__drawer--sort", html)
        self.assertIn("data-filter-toggle", html)
        self.assertIn("data-sort-toggle", html)

    def test_store_base_renders_live_style_footer(self):
        response = self.client.get("/store")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("class=\"footer\"", html)
        self.assertIn("footer__colors", html)
        self.assertIn("footer-newsletter", html)
        self.assertIn("footer-nav__tabset", html)

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
        self.assertIn("cart-page__checkout button button--blue", html)
        self.assertIn("cart-page__gift", html)

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
