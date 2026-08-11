"""Scraper for Cycling Ireland ranking data from the public API."""

import re
import time

import requests
from bs4 import BeautifulSoup

from config import API_BASE, CATEGORIES


session = requests.Session()
session.headers.update(
    {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html, */*",
    }
)


def scrape_rankings(category: str) -> list[dict]:
    """Fetch and parse the ranking table for a single category.

    Returns a list of dicts with keys:
        rank, competition_category, rider_category, name, club, gender,
        points, is_provisional, uuid
    """
    url = f"{API_BASE}/api/ranking-table.html?rank={category}"
    resp = session.get(url, timeout=30)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "lxml")
    rows = soup.select("table tr")

    riders = []
    for tr in rows:
        tds = tr.find_all("td")
        if len(tds) != 8:
            continue

        rank = tds[0].get_text(strip=True)
        comp_cat = tds[1].get_text(strip=True)
        rider_cat = tds[2].get_text(strip=True)
        name = tds[3].get_text(strip=True)
        club = tds[4].get_text(strip=True)
        gender = tds[5].get_text(strip=True)
        points_raw = tds[6].get_text(strip=True)

        # Extract UUID from the View button
        button = tds[7].find("button")
        uuid = None
        if button and button.get("onclick"):
            m = re.search(r"'([^']+)'", button["onclick"])
            if m:
                uuid = m.group(1)

        # Points can have a trailing "*" for provisional
        is_provisional = points_raw.endswith("*")
        points = points_raw.rstrip("*")

        riders.append(
            {
                "rank": int(rank),
                "competition_category": comp_cat,
                "rider_category": rider_cat,
                "name": name,
                "club": club,
                "gender": gender,
                "points": points,
                "is_provisional": int(is_provisional),
                "uuid": uuid,
            }
        )

    return riders


def scrape_all_rankings(
    categories: list[str] | None = None,
    delay: float = 1.0,
    progress_callback=None,
) -> dict[str, list[dict]]:
    """Scrape rankings for all given categories (defaults to all)."""
    categories = categories or CATEGORIES
    results: dict[str, list[dict]] = {}

    for cat in categories:
        try:
            riders = scrape_rankings(cat)
            results[cat] = riders
            if progress_callback:
                progress_callback(cat, len(riders))
            time.sleep(delay)
        except Exception as e:
            print(f"  [ERROR] {cat}: {e}")
            results[cat] = []

    return results


def scrape_rider_details(uuid: str) -> dict | None:
    """Fetch detailed info and race results for a single rider.

    Returns dict with keys:
        name, club, competition_category, total_points, race_results
    """
    url = f"{API_BASE}/api/participant-info.html?uuid={uuid}"
    resp = session.get(url, timeout=30)
    if resp.status_code != 200:
        return None

    soup = BeautifulSoup(resp.text, "lxml")

    # Profile info
    name = _extract_h4(soup, "Profile Full Name")
    club = _extract_h4(soup, "Club/Team Name")
    comp_cat = _extract_h4(soup, "Competition Category")
    total_points = _extract_h4(soup, "Total Points")

    # Race results per year
    race_results = []
    for year_div in soup.select("tbody.year-places"):
        year = year_div.get("data-year")
        if year:
            year = int(year)
        for tr in year_div.find_all("tr"):
            tds = tr.find_all("td")
            if len(tds) < 5:
                continue
            race_results.append(
                {
                    "race_date": tds[0].get_text(strip=True),
                    "event_name": tds[1].get_text(strip=True),
                    "race_name": tds[2].get_text(strip=True),
                    "position": tds[3].get_text(strip=True),
                    "points": tds[4].get_text(strip=True),
                    "year": year,
                }
            )

    return {
        "uuid": uuid,
        "name": name,
        "club": club,
        "competition_category": comp_cat,
        "total_points": total_points,
        "race_results": race_results,
    }


def _extract_h4(soup: BeautifulSoup, label: str) -> str | None:
    """Extract text from an <h4> containing *label*."""
    for h4 in soup.find_all("h4"):
        text = h4.get_text(strip=True)
        if label in text:
            # Strip "Label: " prefix
            parts = text.split(":", 1)
            return parts[1].strip() if len(parts) > 1 else ""
    return None