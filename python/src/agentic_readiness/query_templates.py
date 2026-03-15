"""Query templates for Phase 4 query-driven visibility analysis."""

CATEGORIES = ("generic", "apparel")

# Curated countries for location/locale targeting (ISO 3166-1 alpha-2)
COUNTRIES = [
    ("US", "United States"),
    ("GB", "United Kingdom"),
    ("DE", "Germany"),
    ("FR", "France"),
    ("ES", "Spain"),
    ("IT", "Italy"),
    ("NL", "Netherlands"),
    ("BE", "Belgium"),
    ("AT", "Austria"),
    ("CH", "Switzerland"),
    ("PL", "Poland"),
    ("SE", "Sweden"),
    ("NO", "Norway"),
    ("DK", "Denmark"),
    ("FI", "Finland"),
    ("IE", "Ireland"),
    ("PT", "Portugal"),
    ("JP", "Japan"),
    ("AU", "Australia"),
    ("IN", "India"),
    ("CN", "China"),
    ("KR", "South Korea"),
    ("SG", "Singapore"),
    ("CA", "Canada"),
    ("MX", "Mexico"),
    ("BR", "Brazil"),
    ("AR", "Argentina"),
    ("ZA", "South Africa"),
    ("AE", "United Arab Emirates"),
    ("TR", "Turkey"),
    ("RU", "Russia"),
]

COUNTRY_CODES = {c[0] for c in COUNTRIES}
COUNTRY_NAMES = dict(COUNTRIES)


def get_country_name(code: str) -> str:
    """Return display name for country code, or the code itself if unknown."""
    return COUNTRY_NAMES.get((code or "").strip().upper(), code or "")

APPAREL_QUERIES = [
    "waterproof jacket",
    "water-repellent jacket",
    "packable jacket",
    "ski jacket for beginners",
]

GENERIC_QUERIES = [
    "best brands in category",
]

MAX_QUERY_LENGTH = 200


def get_queries_for_category(category: str) -> list[str]:
    """Return predefined queries for the given category."""
    cat = (category or "generic").strip().lower()
    if cat == "apparel":
        return list(APPAREL_QUERIES)
    return list(GENERIC_QUERIES)


def validate_query_text(query_text: str) -> str | None:
    """
    Validate query_text. Returns None if valid; otherwise returns error message.
    Allows custom queries not in predefined list (max 200 chars).
    """
    q = (query_text or "").strip()
    if not q:
        return "query_text is required and cannot be empty"
    if len(q) > MAX_QUERY_LENGTH:
        return f"query_text must be at most {MAX_QUERY_LENGTH} characters"
    return None
