from __future__ import annotations

import json
import time
import re
from dataclasses import dataclass
from typing import Any, Callable, Dict
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup, Tag


AMBIGUITY_TERMS = ["best", "great", "awesome", "premium", "high quality", "top", "perfekt", "ideal"]
ATTRIBUTE_KEYWORDS = {
    "material": ["material", "stoffe", "stoff", "fabric", "materiale"],
    "size": ["size", "sizes", "groesse", "größe", "taille", "talla"],
    "color": ["color", "colour", "farbe", "couleur", "colore"],
    "fit": ["fit", "passform", "schnitt"],
    "sku": ["sku", "artikelnummer", "art.-nr", "item no"],
    "brand": ["brand", "marke", "hersteller"],
    "model": ["model", "modell"],
    "weight": ["weight", "gewicht", "poids", "peso"],
}
SPEC_PATTERN = re.compile(r"\b[a-zA-ZäöüÄÖÜß][\wäöüÄÖÜß\s-]{2,30}\s*[:\-]\s*[\w\d%.,/+\-\s]{1,40}")
DIRECT_ANSWER_PATTERN = re.compile(
    r"\b(the|a|an)\s+\w+\s+is\s+|\byou\s+can\s+|\bit\s+is\s+|\bthis\s+(?:product|item)\s+|"
    r"\bdas\s+\w+\s+ist\s+|\bsie\s+k[oö]nnen\s+|\bdu\s+kannst\s+",
    re.I,
)


@dataclass(frozen=True)
class FetchResult:
    html: str
    meta: Dict[str, Any]


def _domain_from_url(url: str) -> str:
    try:
        parsed = urlparse(url)
        host = (parsed.netloc or "").lower()
        return host.split(":")[0] if host else ""
    except Exception:
        return ""


def validate_url(url: str, timeout_sec: int = 10) -> None:
    """Validate URL before any LLM call (TASK 2b.4). Raises ValueError with message on failure."""
    u = (url or "").strip()
    if not u:
        raise ValueError("URL is required.")
    parsed = urlparse(u)
    scheme = (parsed.scheme or "https").lower()
    if scheme not in ("http", "https"):
        raise ValueError("URL must use http or https.")
    host = (parsed.netloc or "").strip()
    if not host:
        raise ValueError("URL must have a valid host.")
    if len(u) > 2048:
        raise ValueError("URL too long.")
    try:
        req = Request(
            u,
            method="GET",
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
                )
            },
        )
        with urlopen(req, timeout=timeout_sec) as resp:
            code = getattr(resp, "status", None) or getattr(resp, "code", 200)
            if code >= 400 and code != 403:
                raise ValueError(f"Server returned {code}.")
            body = resp.read(65536)
    except HTTPError as e:
        if e.code == 403:
            return
        raise ValueError(f"Server returned {e.code}.") from e
    except URLError as e:
        msg = str(e.reason or e).lower()
        if "timeout" in msg or "timed out" in msg:
            raise ValueError("URL could not be reached (timeout).") from e
        raise ValueError("URL could not be reached.") from e
    except TimeoutError as e:
        raise ValueError("URL could not be reached (timeout).") from e
    if len(body) < 2048:
        try:
            text = body.decode("utf-8", errors="ignore").lower()
            if any(
                x in text
                for x in (
                    "javascript is disabled",
                    "enable javascript",
                    "please enable js",
                    "enable js",
                )
            ):
                raise ValueError("Page requires JavaScript; we cannot analyze it.")
        except ValueError:
            raise
        except Exception:
            pass


def _normalize_url_token(url: str) -> str:
    return (url or "").strip().lower().replace("%20", " ")


def _tokenize(text: str) -> set[str]:
    clean = re.sub(r"[^a-z0-9äöüß\s]", " ", (text or "").lower())
    return {t for t in clean.split() if len(t) > 2}


def _jaccard(a: str, b: str) -> float:
    sa = _tokenize(a)
    sb = _tokenize(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / max(1, len(sa | sb))


def _safe_json_loads(raw: str) -> Any:
    try:
        return json.loads(raw)
    except Exception:
        return None


def _flatten_jsonld(node: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if isinstance(node, list):
        for item in node:
            out.extend(_flatten_jsonld(item))
        return out
    if not isinstance(node, dict):
        return out

    out.append(node)
    graph = node.get("@graph")
    if graph is not None:
        out.extend(_flatten_jsonld(graph))
    return out


def fetch_html(
    url: str, timeout_sec: int = 30, progress_hook: Callable[[str, int], None] | None = None
) -> FetchResult:
    if progress_hook:
        progress_hook("Trying standard HTTP fetch...", 20)
    request = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            )
        },
    )
    try:
        with urlopen(request, timeout=timeout_sec) as response:
            html = response.read().decode("utf-8", errors="ignore")
            return FetchResult(
                html=html,
                meta={
                    "via": "http",
                    "status_code": int(response.getcode() or 200),
                    "html_bytes": len(html.encode("utf-8", errors="ignore")),
                    "render_ok": bool(re.search(r"<html|<body", html, flags=re.I)),
                },
            )
    except HTTPError as exc:
        if exc.code == 403:
            if progress_hook:
                progress_hook("Bot protection detected. Switching to browser fallback...", 35)
            fallback_html, fallback_error, fallback_meta = _fetch_html_via_playwright(
                url, timeout_sec=timeout_sec, progress_hook=progress_hook
            )
            if fallback_html:
                return FetchResult(html=fallback_html, meta=fallback_meta)
            if fallback_error:
                raise RuntimeError(
                    f"Failed to fetch URL (403): {url}. Browser fallback failed: {fallback_error}"
                ) from exc
        raise RuntimeError(f"Failed to fetch URL ({exc.code}): {url}") from exc
    except URLError as exc:
        raise RuntimeError(f"Failed to fetch URL: {url} ({exc.reason})") from exc


def _fetch_html_via_playwright(
    url: str, timeout_sec: int = 30, progress_hook: Callable[[str, int], None] | None = None
) -> tuple[str | None, str | None, Dict[str, Any]]:
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except Exception:
        return (
            None,
            "playwright is not installed. Install with: pip install playwright && python -m playwright install chromium",
            {"via": "playwright", "status_code": None, "html_bytes": 0, "render_ok": False},
        )

    try:
        with sync_playwright() as p:
            if progress_hook:
                progress_hook("Launching headless browser...", 40)
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122.0.0.0 Safari/537.36"
                ),
                locale="de-DE",
            )
            page = context.new_page()
            if progress_hook:
                progress_hook("Loading page in browser fallback...", 48)
            try:
                # "commit" is resilient for bot-protected pages where domcontentloaded can hang.
                page.goto(url, wait_until="commit", timeout=timeout_sec * 1000)
            except PlaywrightTimeoutError:
                # If navigation technically timed out but page already has content, keep going.
                pass
            if progress_hook:
                progress_hook("Extracting rendered content...", 56)
            content = None
            for _ in range(6):
                try:
                    content = page.content()
                    if content and "<html" in content.lower():
                        break
                except Exception:
                    pass
                page.wait_for_timeout(600)
                time.sleep(0.05)
            if not content:
                content = page.content()
            context.close()
            browser.close()
            return (
                content,
                None,
                {
                    "via": "playwright",
                    "status_code": 200,
                    "html_bytes": len((content or "").encode("utf-8", errors="ignore")),
                    "render_ok": bool(re.search(r"<html|<body", content or "", flags=re.I)),
                },
            )
    except Exception as exc:
        return None, str(exc), {"via": "playwright", "status_code": None, "html_bytes": 0, "render_ok": False}


def _get_meta_content(soup: BeautifulSoup, key: str, attr: str = "name") -> str:
    for tag in soup.find_all("meta"):
        value = tag.get(attr)
        if isinstance(value, str) and value.strip().lower() == key.lower():
            content = tag.get("content")
            return str(content).strip() if content else ""
    return ""


def _extract_jsonld_nodes(soup: BeautifulSoup) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    for script in soup.find_all("script", attrs={"type": re.compile(r"application/ld\+json", re.I)}):
        payload = _safe_json_loads(script.string or script.get_text() or "")
        if payload is None:
            continue
        nodes.extend(_flatten_jsonld(payload))
    return nodes


def _first_text(node: Tag | None) -> str:
    if not node:
        return ""
    return re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip()


def _main_content_node(soup: BeautifulSoup) -> Tag:
    direct_main = soup.find("main")
    if isinstance(direct_main, Tag):
        return direct_main

    role_main = soup.find(attrs={"role": re.compile(r"main", re.I)})
    if isinstance(role_main, Tag):
        return role_main

    article = soup.find("article")
    if isinstance(article, Tag):
        return article

    body = soup.body if isinstance(soup.body, Tag) else soup
    candidates = body.find_all(["section", "div"], recursive=True)
    best = body
    best_score = 0
    for candidate in candidates:
        classes = " ".join(candidate.get("class", [])).lower()
        ident = (candidate.get("id") or "").lower()
        if any(k in classes or k in ident for k in ["footer", "header", "nav", "cookie", "consent", "menu"]):
            continue
        text_len = len(_first_text(candidate))
        p_count = len(candidate.find_all("p"))
        score = text_len + (p_count * 40)
        if score > best_score:
            best_score = score
            best = candidate
    return best


def _strip_boilerplate(node: Tag) -> None:
    for noisy in node.find_all(["nav", "header", "footer", "aside"]):
        noisy.decompose()
    for noisy in node.find_all(attrs={"class": re.compile(r"cookie|consent|newsletter|subscribe", re.I)}):
        noisy.decompose()


def _detect_page_type(url: str, schema_types: set[str], h1: str, main_text: str) -> str:
    u = _normalize_url_token(url)
    if any(t in schema_types for t in ["product"]):
        return "pdp"
    if any(t in schema_types for t in ["article", "blogposting", "newsarticle"]):
        return "article"
    if "itemlist" in schema_types or re.search(r"/(collection|category|kategorie|shop|products?)/", u):
        return "plp_category"
    if re.search(r"/(home|index)?/?$", u) and len(u.rstrip("/").split("/")) <= 3:
        return "homepage"
    if h1 and re.search(r"\b(blog|guide|faq)\b", h1, flags=re.I):
        return "article"
    if main_text.count("€") > 3 and main_text.count("\n") > 1:
        return "plp_category"
    return "unknown"


def _extract_schema_entities(nodes: list[dict[str, Any]]) -> dict[str, Any]:
    schema_types: set[str] = set()
    product_names: list[str] = []
    brands: list[str] = []
    offers_present = 0
    offer_price_present = 0
    offer_availability_present = 0
    review_present = 0

    for node in nodes:
        node_type = node.get("@type")
        types = [node_type] if isinstance(node_type, str) else node_type if isinstance(node_type, list) else []
        types = [str(t).lower() for t in types]
        schema_types.update(types)

        if "product" in types:
            name = node.get("name")
            if isinstance(name, str) and name.strip():
                product_names.append(name.strip())

            brand = node.get("brand")
            if isinstance(brand, dict):
                brand_name = brand.get("name")
                if isinstance(brand_name, str) and brand_name.strip():
                    brands.append(brand_name.strip())
            elif isinstance(brand, str) and brand.strip():
                brands.append(brand.strip())

            offers = node.get("offers")
            offers_list = offers if isinstance(offers, list) else [offers] if isinstance(offers, dict) else []
            if offers_list:
                offers_present += 1
            for offer in offers_list:
                if not isinstance(offer, dict):
                    continue
                if offer.get("price") is not None and str(offer.get("price")).strip():
                    offer_price_present += 1
                if offer.get("availability"):
                    offer_availability_present += 1

            if node.get("review") or node.get("aggregateRating"):
                review_present += 1

    return {
        "schema_types": schema_types,
        "product_names": product_names,
        "brands": brands,
        "offers_present": offers_present,
        "offer_price_present": offer_price_present,
        "offer_availability_present": offer_availability_present,
        "review_present": review_present,
    }


def _attribute_completeness(text: str) -> float:
    text_l = (text or "").lower()
    matched = 0
    for _, variants in ATTRIBUTE_KEYWORDS.items():
        if any(v in text_l for v in variants):
            matched += 1
    return min(1.0, matched / max(1, len(ATTRIBUTE_KEYWORDS)))


def _build_product_from_url_html(
    url: str,
    html: str,
    fetch_meta: Dict[str, Any] | None = None,
    progress_hook: Callable[[str, int], None] | None = None,
) -> Dict[str, Any]:
    if progress_hook:
        progress_hook("Parsing page structure...", 60)
    soup = BeautifulSoup(html or "", "lxml")
    title = _first_text(soup.title)
    meta_desc = _get_meta_content(soup, "description", attr="name")
    canonical = ""
    for tag in soup.find_all("link"):
        rel = tag.get("rel")
        rel_tokens = [str(x).lower() for x in (rel or [])] if isinstance(rel, list) else [str(rel).lower()] if rel else []
        if "canonical" in rel_tokens:
            canonical = str(tag.get("href") or "").strip()
            break

    og_title = _get_meta_content(soup, "og:title", attr="property")
    og_desc = _get_meta_content(soup, "og:description", attr="property")
    og_image = _get_meta_content(soup, "og:image", attr="property")
    og_type = _get_meta_content(soup, "og:type", attr="property")
    robots = _get_meta_content(soup, "robots", attr="name")

    if progress_hook:
        progress_hook("Extracting schema and metadata...", 65)
    jsonld_nodes = _extract_jsonld_nodes(soup)
    schema = _extract_schema_entities(jsonld_nodes)
    schema_types = schema["schema_types"]

    total_text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True)).strip()

    main_node = _main_content_node(soup)
    main_clone = BeautifulSoup(str(main_node), "lxml")
    main_tag = main_clone.find() if main_clone.find() else main_clone
    if isinstance(main_tag, Tag):
        _strip_boilerplate(main_tag)
        main_text = re.sub(r"\s+", " ", main_tag.get_text(" ", strip=True)).strip()
    else:
        main_text = total_text
    effective_text = main_text or total_text

    h1_nodes = soup.find_all("h1")
    h2_nodes = soup.find_all("h2")
    h1_count = len(h1_nodes)
    h1_text = _first_text(h1_nodes[0]) if h1_nodes else ""

    img_nodes = soup.find_all("img")
    img_count = len(img_nodes)
    img_alt_nonempty = sum(1 for img in img_nodes if str(img.get("alt") or "").strip())

    contains_price_hint = bool(re.search(r"\bEUR\b|\$|€|\bpreis\b|\bprice\b", total_text, flags=re.I))
    page_domain = _domain_from_url(url)
    canonical_domain = _domain_from_url(canonical) if canonical else ""
    canonical_present = bool(canonical)
    canonical_self_ref = canonical_present and (page_domain == canonical_domain)
    hreflang_present = bool(
        soup.find("link", attrs={"rel": re.compile(r"alternate", re.I), "hreflang": True})
    )
    robots_lower = (robots or "").lower()
    robots_valid = "noindex" not in robots_lower

    all_links = soup.find_all("a", href=True)
    internal_link_count = 0
    external_link_count = 0
    for link in all_links:
        href = str(link.get("href") or "").strip().split("#")[0]
        if not href or href.startswith("javascript:") or href.startswith("mailto:"):
            continue
        href_no_query = href.split("?")[0]
        if href_no_query.startswith("/") or _domain_from_url(href_no_query) == page_domain:
            internal_link_count += 1
        else:
            external_link_count += 1

    list_count = len(main_node.find_all(["ul", "ol"])) if isinstance(main_node, Tag) else 0
    block_count = len(main_node.find_all(["p", "div", "ul", "ol", "table"])) if isinstance(main_node, Tag) else 1
    list_structure_ratio = min(1.0, list_count / max(3, block_count / 5))
    table_presence = bool(main_node.find("table")) if isinstance(main_node, Tag) else False

    paragraph_nodes = main_node.find_all("p") if isinstance(main_node, Tag) else []
    paragraph_texts = [_first_text(p) for p in paragraph_nodes if _first_text(p)]
    word_counts = [len(p.split()) for p in paragraph_texts]
    total_paras = len(word_counts) or 1
    concise_paras = sum(1 for w in word_counts if 0 < w <= 50)
    concise_paragraph_ratio = min(1.0, concise_paras / total_paras)
    direct_hits = sum(1 for p in paragraph_texts if DIRECT_ANSWER_PATTERN.search(p))
    direct_answer_patterns = min(1.0, direct_hits / max(2, total_paras))
    question_sentences = len(re.findall(r"[^.!?]*\?+", effective_text))
    question_coverage = min(1.0, question_sentences / 3.0)
    spec_hits = len(SPEC_PATTERN.findall(effective_text))

    og_coverage = sum(bool(x) for x in [og_title, og_desc, og_image, og_type]) / 4.0
    image_alt_ratio = min(1.0, max(0.0, (img_alt_nonempty / img_count) if img_count else 0.0))
    media_quality = min(1.0, image_alt_ratio)

    if progress_hook:
        progress_hook("Analyzing content...", 72)
    page_type = _detect_page_type(url, schema_types, h1_text, effective_text)

    product_names = schema["product_names"]
    brands = schema["brands"]
    schema_name = product_names[0] if product_names else ""
    schema_brand = brands[0] if brands else ""
    source_entities = [x for x in [title, h1_text, og_title, schema_name, schema_brand] if x]
    pair_scores = []
    for i in range(len(source_entities)):
        for j in range(i + 1, len(source_entities)):
            pair_scores.append(_jaccard(source_entities[i], source_entities[j]))
    entity_consistency = sum(pair_scores) / len(pair_scores) if pair_scores else 0.35
    entity_consistency = min(1.0, max(0.0, entity_consistency))

    factual_checks = []
    if schema_name:
        factual_checks.append(1.0 if _jaccard(schema_name, title or h1_text) >= 0.2 else 0.0)
    if schema_brand:
        factual_checks.append(1.0 if schema_brand.lower() in (effective_text or "").lower() else 0.0)
    if schema["offer_price_present"] > 0:
        factual_checks.append(1.0 if contains_price_hint else 0.0)
    if schema["offer_availability_present"] > 0:
        factual_checks.append(1.0 if re.search(r"in stock|out of stock|verf[üu]gbar|lieferbar", effective_text, re.I) else 0.0)
    factual_grounding = sum(factual_checks) / len(factual_checks) if factual_checks else 0.4
    factual_grounding = min(1.0, max(0.0, factual_grounding))

    answerability_components = [
        0.35 * min(1.0, len(effective_text.split()) / 350.0),
        0.25 * direct_answer_patterns,
        0.20 * min(1.0, spec_hits / 6.0),
        0.20 * min(1.0, question_coverage),
    ]
    query_answerability = min(1.0, max(0.0, sum(answerability_components)))

    ambiguity_count = sum(effective_text.lower().count(term) for term in AMBIGUITY_TERMS)
    main_word_count = len(effective_text.split())
    total_word_count = len(total_text.split())
    attribute_completeness = _attribute_completeness(effective_text)

    schema_required_hits = 0
    schema_required_total = 5
    schema_required_hits += 1 if "product" in schema_types else 0
    schema_required_hits += 1 if schema_name else 0
    schema_required_hits += 1 if schema_brand else 0
    schema_required_hits += 1 if schema["offer_price_present"] > 0 else 0
    schema_required_hits += 1 if schema["offer_availability_present"] > 0 else 0
    required_field_coverage = schema_required_hits / schema_required_total

    low_content = total_word_count < 50 and not title
    llm_variance = 25 if low_content else 0

    product = {
        "product_id": f"url::{url}",
        "url": url,
        "has_feed": False,
        "prevalence": 1.0,
        "fetch": fetch_meta or {"via": "unknown", "status_code": None, "html_bytes": len((html or "").encode("utf-8")), "render_ok": bool(title)},
        "schema": {
            "product_present": "product" in schema_types,
            "required_field_coverage": round(required_field_coverage, 4),
        },
        "page": {
            "indexable": "noindex" not in robots_lower,
            "og_coverage": round(og_coverage, 4),
            "url_hygiene": not bool(re.search(r"utm_|session|ref=", (canonical or url).lower())),
            "price_availability_machine_readable": bool(schema["offer_price_present"] > 0 and schema["offer_availability_present"] > 0),
            "variant_clarity": bool(
                re.search(r"\bsize\b|\bcolor\b|\bvariant\b|\bgröße\b|\bgroesse\b|\bfarbe\b", effective_text, flags=re.I)
            ),
            "page_type": page_type,
        },
        "content": {
            "title_length": len(title),
            "description_length": len(meta_desc),
            "attribute_completeness": round(attribute_completeness, 4),
            "pricing_clarity": contains_price_hint,
            "policy_clarity": bool(re.search(r"\breturn\b|\bshipping\b|\bdelivery\b|\brückgabe\b|\bversand\b", effective_text, flags=re.I)),
            "review_presence": bool(
                re.search(r"\brating\b|\breview\b|\bbewertung\b", effective_text, flags=re.I) or schema["review_present"] > 0
            ),
            "support_trust_info": bool(re.search(r"\bwarranty\b|\bguarantee\b|\bkontakt\b|\bsupport\b", effective_text, flags=re.I)),
            "content_word_count": main_word_count,
            "total_word_count": total_word_count,
        },
        "semantic": {
            "ambiguity_count": ambiguity_count,
            "entity_consistency": round(entity_consistency, 4),
            "query_answerability": round(query_answerability, 4),
            "factual_grounding": round(factual_grounding, 4),
            "llm_variance": llm_variance,
        },
        "ux": {
            "render_accessibility": bool(soup.find("body")),
            "core_discoverability": bool(title or h1_text),
            "media_quality": round(media_quality, 4),
            "mobile_readability": bool(_get_meta_content(soup, "viewport", attr="name")),
        },
        "aeo": {
            "faq_schema_present": "faqpage" in schema_types,
            "howto_schema_present": "howto" in schema_types,
            "direct_answer_patterns": round(direct_answer_patterns, 4),
            "list_structure_ratio": round(list_structure_ratio, 4),
            "table_presence": table_presence,
            "heading_hierarchy_valid": (h1_count == 1 and len(h2_nodes) >= 0),
            "concise_paragraph_ratio": round(concise_paragraph_ratio, 4),
            "question_coverage": round(question_coverage, 4),
        },
        "seo": {
            "h1_count": h1_count,
            "h1_present": h1_count > 0,
            "meta_desc_present": bool(meta_desc and meta_desc.strip()),
            "meta_desc_length": len(meta_desc),
            "canonical_present": canonical_present,
            "canonical_self_ref": canonical_self_ref,
            "hreflang_present": hreflang_present,
            "internal_link_count": internal_link_count,
            "external_link_count": external_link_count,
            "word_count": main_word_count,
            "image_alt_ratio": round(image_alt_ratio, 4),
            "robots_valid": robots_valid,
        },
        "evidence": {
            "page_type": page_type,
            "schema_types": sorted(schema_types),
            "entities": {
                "title": title,
                "h1": h1_text,
                "og_title": og_title,
                "schema_name": schema_name,
                "schema_brand": schema_brand,
                "canonical": canonical,
                "meta_description_length": len(meta_desc),
            },
            "segmentation": {
                "main_word_count": main_word_count,
                "total_word_count": total_word_count,
            },
        },
    }
    return product


def build_product_from_url_html(url: str, html: str, progress_hook: Callable[[str, int], None] | None = None) -> Dict[str, Any]:
    return _build_product_from_url_html(url, html, fetch_meta=None, progress_hook=progress_hook)


def load_single_url_product(
    url: str, timeout_sec: int = 30, progress_hook: Callable[[str, int], None] | None = None
) -> Dict[str, Any]:
    fetched = fetch_html(url, timeout_sec=timeout_sec, progress_hook=progress_hook)
    return _build_product_from_url_html(url, fetched.html, fetch_meta=fetched.meta, progress_hook=progress_hook)


def dump_product_debug(product: Dict[str, Any]) -> str:
    return json.dumps(product, indent=2, ensure_ascii=False)
