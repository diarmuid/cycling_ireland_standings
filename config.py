"""Shared configuration for the Cycling Ireland Rankings scraper."""

API_BASE = "https://membership.cyclingireland.ie"

CATEGORIES = [
    "C1",
    "C2",
    "C3",
    "JC1",
    "JC2",
    "JC3",
    "WMN",
    "U16",
]

CATEGORY_LABELS = {
    "C1": "Category 1",
    "C2": "Category 2",
    "C3": "Category 3",
    "JC1": "Junior C1",
    "JC2": "Junior C2",
    "JC3": "Junior C3",
    "WMN": "Women",
    "U16": "Under 16",
}

DB_PATH = "rankings.db"