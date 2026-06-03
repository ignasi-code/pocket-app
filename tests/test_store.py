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
        self.assertIn("/store/api/checkout", html)

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
