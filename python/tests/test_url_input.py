from __future__ import annotations

import unittest

from agentic_readiness.url_input import build_product_from_url_html


class UrlInputTests(unittest.TestCase):
    def test_build_product_from_html(self) -> None:
        html = """
        <html>
          <head>
            <title>Product Name Example</title>
            <meta name=\"description\" content=\"A detailed product description with specs and use cases.\" />
            <meta property=\"og:title\" content=\"Product Name Example\" />
            <meta property=\"og:description\" content=\"OG Description\" />
            <meta property=\"og:image\" content=\"https://example.com/a.jpg\" />
            <meta property=\"og:type\" content=\"product\" />
            <meta name=\"viewport\" content=\"width=device-width\" />
            <script type=\"application/ld+json\">{"@type":"Product","name":"Product Name Example","brand":{"name":"Acme"},"offers":{"price":"10","availability":"InStock"}}</script>
          </head>
          <body>
            <h1>Product Name Example</h1>
            <img src=\"a.jpg\" alt=\"Product image\" />
            Price: 10 EUR
            color size material brand model shipping return support rating review
          </body>
        </html>
        """
        product = build_product_from_url_html("https://example.com/p/1", html)
        self.assertEqual(product["url"], "https://example.com/p/1")
        self.assertTrue(product["schema"]["product_present"])
        self.assertGreaterEqual(product["page"]["og_coverage"], 1.0)
        self.assertGreater(product["content"]["description_length"], 10)
        self.assertTrue(product["ux"]["mobile_readability"])
        self.assertEqual(product["page"]["page_type"], "pdp")
        self.assertGreaterEqual(product["schema"]["required_field_coverage"], 0.8)

    def test_meta_description_attribute_order_is_supported(self) -> None:
        html = """
        <html>
          <head>
            <title>Order Test</title>
            <meta content=\"Meta text from swapped attribute order.\" name=\"description\" />
            <meta property=\"og:title\" content=\"Order Test\" />
            <meta property=\"og:type\" content=\"website\" />
          </head>
          <body><h1>Order Test</h1></body>
        </html>
        """
        product = build_product_from_url_html("https://example.com/order", html)
        self.assertEqual(product["content"]["description_length"], len("Meta text from swapped attribute order."))

    def test_german_attribute_keywords_count_toward_completeness(self) -> None:
        html = """
        <html>
          <head><title>Skijacke</title><meta property=\"og:type\" content=\"product\" /></head>
          <body>
            <main>
              <h1>Skijacke</h1>
              <p>Marke: BOSS</p>
              <p>Material: Polyamid</p>
              <p>Größe: L</p>
              <p>Farbe: Schwarz</p>
              <p>Passform: Regular Fit</p>
            </main>
          </body>
        </html>
        """
        product = build_product_from_url_html("https://example.com/de/skijacke", html)
        self.assertGreater(product["content"]["attribute_completeness"], 0.4)

    def test_category_url_detected_as_plp(self) -> None:
        html = """
        <html>
          <head><title>Ski Collection</title><meta property=\"og:type\" content=\"website\" /></head>
          <body><main><h1>Ski Collection</h1><p>€ 100</p><p>€ 120</p><p>€ 140</p><p>€ 170</p></main></body>
        </html>
        """
        product = build_product_from_url_html("https://example.com/category/ski-kollektion/", html)
        self.assertEqual(product["page"]["page_type"], "plp_category")

    def test_low_content_increases_llm_variance(self) -> None:
        product = build_product_from_url_html("https://example.com/empty", "<html><body></body></html>")
        self.assertGreaterEqual(product["semantic"]["llm_variance"], 20)


if __name__ == "__main__":
    unittest.main()
