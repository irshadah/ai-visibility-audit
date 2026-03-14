from __future__ import annotations

import csv
import json
from pathlib import Path
import re
from typing import Any, Dict, List, Optional
import xml.etree.ElementTree as ET


RE_PRICE_WITH_CURRENCY = re.compile(r"^\s*\d+(?:\.\d{1,2})?\s+[A-Z]{3}\s*$")


def read_json(path: str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: str, data: Any) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_previous(path: Optional[str]) -> Optional[Dict[str, Any]]:
    if not path:
        return None
    return read_json(path)


def load_products(input_path: str, input_type: str = "auto") -> List[Dict[str, Any]]:
    resolved_type = input_type if input_type != "auto" else detect_input_type(input_path)

    if resolved_type == "normalized_json":
        data = read_json(input_path)
        if isinstance(data, dict) and "products" in data:
            return data["products"]
        if isinstance(data, list):
            return data
        raise ValueError("Normalized JSON must be array or object with 'products'.")

    if resolved_type == "merchant_json":
        rows = parse_merchant_json(input_path)
        return normalize_merchant_rows(rows)

    if resolved_type == "merchant_csv":
        rows = parse_merchant_csv(input_path)
        return normalize_merchant_rows(rows)

    if resolved_type == "merchant_xml":
        rows = parse_merchant_xml(input_path)
        return normalize_merchant_rows(rows)

    raise ValueError(f"Unsupported input type: {resolved_type}")


def detect_input_type(input_path: str) -> str:
    suffix = Path(input_path).suffix.lower()
    if suffix == ".csv":
        return "merchant_csv"
    if suffix == ".xml":
        return "merchant_xml"
    if suffix == ".json":
        payload = read_json(input_path)
        if isinstance(payload, dict) and "products" in payload:
            return "normalized_json"
        if isinstance(payload, list) and payload and isinstance(payload[0], dict) and "product_id" in payload[0]:
            return "normalized_json"
        return "merchant_json"
    raise ValueError(f"Cannot infer input type for extension: {suffix}")


def parse_merchant_json(path: str) -> List[Dict[str, Any]]:
    data = read_json(path)
    if isinstance(data, list):
        return [ensure_string_keys(row) for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        for key in ("items", "products", "entries"):
            rows = data.get(key)
            if isinstance(rows, list):
                return [ensure_string_keys(row) for row in rows if isinstance(row, dict)]
    raise ValueError("Merchant JSON feed must be list or object containing list in items/products/entries.")


def parse_merchant_csv(path: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            rows.append({str(k): (v or "") for k, v in row.items() if k is not None})
    return rows


def parse_merchant_xml(path: str) -> List[Dict[str, Any]]:
    tree = ET.parse(path)
    root = tree.getroot()
    items = root.findall(".//item")
    rows: List[Dict[str, Any]] = []
    for item in items:
        row: Dict[str, Any] = {}
        for child in item:
            key = child.tag.split("}")[-1]
            row[key] = (child.text or "").strip()
        rows.append(row)
    return rows


def ensure_string_keys(row: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for key, value in row.items():
        out[str(key)] = value
    return out


def normalize_merchant_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [normalize_merchant_row(row) for row in rows]


def normalize_merchant_row(row: Dict[str, Any]) -> Dict[str, Any]:
    feed = canonicalize_row(row)

    required_fields = [
        "id",
        "title",
        "description",
        "link",
        "image_link",
        "availability",
        "price",
        "condition",
    ]
    required_present = sum(1 for key in required_fields if bool(feed.get(key)))
    brand_key_present = 1 if (feed.get("brand") or feed.get("gtin") or feed.get("mpn")) else 0
    required_coverage = (required_present + brand_key_present) / (len(required_fields) + 1)

    optional_fields = ["google_product_category", "product_type", "color", "size", "material", "age_group", "gender"]
    optional_present = sum(1 for key in optional_fields if bool(feed.get(key)))
    attribute_completeness = optional_present / len(optional_fields)

    price_valid = bool(RE_PRICE_WITH_CURRENCY.match(feed.get("price", "")))
    url_valid = bool(feed.get("link", "").startswith("http")) and bool(feed.get("image_link", "").startswith("http"))
    enum_valid = feed.get("availability", "") in {"in stock", "out of stock", "preorder", "backorder"}
    validity = (int(price_valid) + int(url_valid) + int(enum_valid)) / 3

    title_length = len(feed.get("title", ""))
    description_length = len(feed.get("description", ""))

    ambiguity_terms = ["best", "great", "awesome", "premium", "high quality"]
    text = f"{feed.get('title', '')} {feed.get('description', '')}".lower()
    ambiguity_count = sum(text.count(term) for term in ambiguity_terms)

    entity_consistency = 0.85 if feed.get("brand") else 0.6
    query_answerability = min(1.0, (description_length / 450.0) * 0.7 + attribute_completeness * 0.3)
    factual_grounding = min(1.0, required_coverage * 0.6 + validity * 0.4)

    url_hygiene = not any(token in feed.get("link", "").lower() for token in ["utm_", "session", "ref="])
    variant_clarity = bool(feed.get("item_group_id") or feed.get("size") or feed.get("color"))

    freshness = 1.0 if feed.get("updated") or feed.get("last_updated") else 0.7

    return {
        "product_id": feed.get("id") or feed.get("item_id") or "",
        "url": feed.get("link") or "",
        "has_feed": True,
        "prevalence": 1.0,
        "schema": {
            "product_present": required_coverage >= 0.55,
            "required_field_coverage": round(required_coverage, 4),
        },
        "page": {
            "indexable": bool(feed.get("link")),
            "og_coverage": 0.5,
            "url_hygiene": url_hygiene,
            "price_availability_machine_readable": bool(feed.get("price") and feed.get("availability")),
            "variant_clarity": variant_clarity,
        },
        "content": {
            "title_length": title_length,
            "description_length": description_length,
            "attribute_completeness": round(attribute_completeness, 4),
            "pricing_clarity": bool(feed.get("price")),
            "policy_clarity": bool(feed.get("shipping") or feed.get("return_policy_label")),
            "review_presence": bool(feed.get("product_rating") or feed.get("review_count")),
            "support_trust_info": bool(feed.get("warranty") or feed.get("return_policy_label")),
        },
        "semantic": {
            "ambiguity_count": ambiguity_count,
            "entity_consistency": round(entity_consistency, 4),
            "query_answerability": round(query_answerability, 4),
            "factual_grounding": round(factual_grounding, 4),
            "llm_variance": 0,
        },
        "ux": {
            "render_accessibility": True,
            "core_discoverability": True,
            "media_quality": 0.75 if feed.get("image_link") else 0.2,
            "mobile_readability": True,
        },
        "feed": {
            "required_coverage": round(required_coverage, 4),
            "attribute_completeness": round(attribute_completeness, 4),
            "validity": round(validity, 4),
            "page_consistency": 0.7,
            "freshness": freshness,
        },
    }


def canonicalize_row(row: Dict[str, Any]) -> Dict[str, str]:
    alias_map = {
        "g:id": "id",
        "g:title": "title",
        "g:description": "description",
        "g:link": "link",
        "g:image_link": "image_link",
        "g:availability": "availability",
        "g:price": "price",
        "g:condition": "condition",
        "g:brand": "brand",
        "g:gtin": "gtin",
        "g:mpn": "mpn",
        "g:google_product_category": "google_product_category",
        "g:product_type": "product_type",
        "g:color": "color",
        "g:size": "size",
        "g:material": "material",
        "g:age_group": "age_group",
        "g:gender": "gender",
        "g:item_group_id": "item_group_id",
    }

    out: Dict[str, str] = {}
    for raw_key, raw_value in row.items():
        k = str(raw_key).strip().lower()
        v = "" if raw_value is None else str(raw_value).strip()
        normalized = alias_map.get(k, k)
        out[normalized] = v

    if out.get("availability"):
        out["availability"] = out["availability"].strip().lower()

    return out
