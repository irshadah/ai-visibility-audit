from __future__ import annotations

from pathlib import Path
import unittest

from agentic_readiness.io import load_products

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "fixtures"


class FeedIngestionTests(unittest.TestCase):
    def test_load_merchant_json(self) -> None:
        products = load_products(str(FIXTURES / "feed.json"), input_type="merchant_json")
        self.assertEqual(len(products), 1)
        self.assertEqual(products[0]["product_id"], "F-100")
        self.assertTrue(products[0]["has_feed"])

    def test_load_merchant_csv(self) -> None:
        products = load_products(str(FIXTURES / "feed.csv"), input_type="merchant_csv")
        self.assertEqual(len(products), 1)
        self.assertEqual(products[0]["product_id"], "F-200")
        self.assertGreater(products[0]["feed"]["required_coverage"], 0.8)

    def test_load_merchant_xml(self) -> None:
        products = load_products(str(FIXTURES / "feed.xml"), input_type="merchant_xml")
        self.assertEqual(len(products), 1)
        self.assertEqual(products[0]["product_id"], "F-300")
        self.assertTrue(products[0]["content"]["pricing_clarity"])

    def test_auto_detect_feed_type(self) -> None:
        products = load_products(str(FIXTURES / "feed.csv"))
        self.assertEqual(products[0]["product_id"], "F-200")


if __name__ == "__main__":
    unittest.main()
