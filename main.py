#!/usr/bin/env python3
"""
Cycling Ireland Rankings CLI

Scrapes rider rankings from the Cycling Ireland public API and stores them
in a SQLite database for querying.

Usage:
    python main.py scrape
    python main.py top [--category C1] [--limit 10]
    python main.py club "Burren Cycling Club" [--category C1]
    python main.py rider NAME
    python main.py clubs
    python main.py stats
"""

import argparse
import sys
import time as time_module
from datetime import datetime, timedelta

from config import CATEGORIES, CATEGORY_LABELS, DELTA_MAX_AGE
from database import get_connection, init_db
from queries import (
    find_riders_by_club,
    get_club_standings,
    get_rider_details,
    get_rider_race_results,
    get_stats,
    get_top_ranked,
    list_clubs,
)
from scraper import scrape_all_rankings, scrape_rider_details

# ── Scrape ──────────────────────────────────────────────────────────────────


def cmd_scrape(args):
    """Scrape all rankings and store in the database."""
    print("Initializing database...")
    conn = get_connection()
    init_db(conn)

    delta = args.delta
    max_age = args.max_age or DELTA_MAX_AGE
    cutoff = datetime.now() - timedelta(seconds=max_age)

    categories_to_scrape = []
    for cat in CATEGORIES:
        if delta:
            row = conn.execute(
                "SELECT MAX(scraped_at) FROM scrape_meta WHERE category = ?",
                (cat,),
            ).fetchone()
            last_scraped = row[0]
            if last_scraped:
                last_dt = datetime.fromisoformat(last_scraped)
                if last_dt >= cutoff:
                    print(f"  {cat:>4s} ({CATEGORY_LABELS.get(cat, cat)}): skipped (scraped {last_dt})")
                    continue
        categories_to_scrape.append(cat)

    if not categories_to_scrape:
        print("All categories are up to date. Nothing to scrape.")
        conn.close()
        return

    def progress(cat, count):
        print(f"  {cat:>4s} ({CATEGORY_LABELS.get(cat, cat)}): {count} riders")

    print("Fetching rankings from Cycling Ireland...")
    results = scrape_all_rankings(
        categories=categories_to_scrape, delay=0.5, progress_callback=progress
    )

    total = 0
    for cat, riders in results.items():
        if not riders:
            continue

        # Replace old rankings for this category with fresh data
        conn.execute(
            "DELETE FROM rankings WHERE competition_category = ?",
            (cat,),
        )

        for r in riders:
            conn.execute(
                """INSERT OR IGNORE INTO riders (uuid, name, club, gender)
                   VALUES (?, ?, ?, ?)""",
                (r["uuid"], r["name"], r["club"], r["gender"]),
            )
            conn.execute(
                """INSERT OR IGNORE INTO rankings
                   (rider_uuid, competition_category, rider_category,
                    rank, points, is_provisional)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    r["uuid"],
                    r["competition_category"],
                    r["rider_category"],
                    r["rank"],
                    r["points"],
                    r["is_provisional"],
                ),
            )

        conn.execute(
            "INSERT INTO scrape_meta (category, rider_count) VALUES (?, ?)",
            (cat, len(riders)),
        )
        total += len(riders)

    conn.commit()

    scraped_uuids = set()
    if args.with_results:
        print("\nScraping race results for all riders from this scrape...")
        for cat, riders in results.items():
            for r in riders:
                scraped_uuids.add(r["uuid"])
        count = scrape_rider_results_for_uuids(conn, list(scraped_uuids))
        print(f"Race results stored: {count}")

    conn.close()
    print(f"\nDone! {total} rankings stored across {len(categories_to_scrape)} categories.")


# ── Rider Details ───────────────────────────────────────────────────────────


def scrape_rider_results_for_uuids(conn, uuids, delay=0.5):
    """Scrape race results for a list of rider UUIDs and store in the database.
    Returns the total number of race results stored. Skips duplicates."""
    total = 0
    for i, uuid in enumerate(uuids):
        details = scrape_rider_details(uuid)
        if not details:
            continue

        if details["name"]:
            conn.execute(
                "UPDATE riders SET name=?, club=? WHERE uuid=?",
                (details["name"], details["club"], uuid),
            )

        for rr in details["race_results"]:
            conn.execute(
                """INSERT OR IGNORE INTO race_results
                   (rider_uuid, event_name, race_name, position,
                    points, race_date, year)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    uuid,
                    rr["event_name"],
                    rr["race_name"],
                    rr["position"],
                    rr["points"],
                    rr["race_date"],
                    rr["year"],
                ),
            )
        total += len(details["race_results"])

        if (i + 1) % 50 == 0:
            conn.commit()

        time_module.sleep(delay)

    conn.commit()
    return total


def cmd_rider_details(args):
    """Scrape per-rider race results."""
    conn = get_connection()

    if args.uuid:
        uuids = [args.uuid]
    elif args.all:
        uuids = [
            row[0]
            for row in conn.execute(
                "SELECT uuid FROM riders"
            ).fetchall()
        ]
        print(f"Fetching details for {len(uuids)} riders...")
    else:
        print("Specify --uuid or --all")
        conn.close()
        return

    count = scrape_rider_results_for_uuids(conn, uuids)

    conn.close()
    print(f"\nDone! {count} race results stored.")


# ── Query commands ─────────────────────────────────────────────────────────


def cmd_top(args):
    """Show top ranked riders in a category."""
    rows = get_top_ranked(args.category, args.limit, gender=args.gender)
    if not rows:
        print(f"No rankings found for category '{args.category}'.")
        return

    label = CATEGORY_LABELS.get(args.category, args.category)
    gender_tag = f" [{args.gender}]" if args.gender else ""
    print(f"\n{'=' * 80}")
    print(f"  Top {len(rows)} — {label}{gender_tag} ({len(rows)} entries)")
    print(f"{'=' * 80}")
    print(f"{'Rank':>5s} {'Name':<25s} {'Club':<30s} {'Rider Cat':<10s} {'Gender':<8s} {'Pts':>5s}")
    print("-" * 85)
    for row in rows:
        prov = "*" if row["is_provisional"] else " "
        print(
            f"{row['rank']:>5d} {row['name']:<25s} {row['club']:<30s}"
            f" {row['rider_category']:<10s} {row['gender']:<8s} {row['points']:>5s}{prov}"
        )
    print()


def cmd_club(args):
    """Find all riders from a given club."""
    rows = find_riders_by_club(args.name, args.category, gender=args.gender)
    if not rows:
        print(f"No riders found for club '{args.name}'.")
        return

    print(f"\n{'=' * 90}")
    print(f"  Riders matching club: {args.name} ({len(rows)} entries)")
    if args.category:
        print(f"  Category: {args.category}")
    if args.gender:
        print(f"  Gender: {args.gender}")
    print(f"{'=' * 90}")
    print(
        f"{'Rank':>5s} {'Name':<25s} {'Club':<30s} "
        f"{'Rider Cat':<10s} {'Gender':<8s} {'Comp':<5s} {'Pts':>5s}"
    )
    print("-" * 95)
    for row in rows:
        prov = "*" if row["is_provisional"] else " "
        print(
            f"{row['rank']:>5d} {row['name']:<25s} {row['club']:<30s} "
            f"{row['rider_category']:<10s} {row['gender']:<8s} {row['competition_category']:<5s} "
            f"{row['points']:>5s}{prov}"
        )
    print()
    print()


def cmd_standings(args):
    """Show club standings — all riders sorted by points descending."""
    rows = get_club_standings(args.name, gender=args.gender)
    if not rows:
        print(f"No riders found for club '{args.name}'.")
        return

    total_riders = len(set(r["name"] for r in rows))
    total_points = sum(int(r["points"]) for r in rows)
    avg_points = total_points / total_riders if total_riders else 0
    best_rank = min(r["rank"] for r in rows)

    print(f"\n{'=' * 95}")
    print(f"  Club standings: {rows[0]['club']}")
    print(f"  Riders: {total_riders}  Total pts: {total_points}  "
          f"Avg: {avg_points:.0f}  Best rank: #{best_rank}")
    if args.gender:
        print(f"  Gender: {args.gender}")
    print(f"{'=' * 95}")
    print(
        f"{'Pts':>5s} {'Name':<25s} {'Rider Cat':<10s} "
        f"{'Comp':<5s} {'Gender':<8s} {'Rank':>5s}"
    )
    print("-" * 95)
    for row in rows:
        prov = "*" if row["is_provisional"] else " "
        print(
            f"{row['points']:>5s}{prov} {row['name']:<25s} "
            f"{row['rider_category']:<10s} {row['competition_category']:<5s} "
            f"{row['gender']:<8s} {row['rank']:>5d}"
        )
    print()


def cmd_rider(args):
    """Look up a rider by name, optionally fetching race results."""
    rows = get_rider_details(args.name, club=args.club)
    if not rows:
        msg = f"No rider found matching '{args.name}'"
        if args.club:
            msg += f" at club '{args.club}'"
        print(msg + ".")
        return

    # Group rows by UUID to detect duplicates
    from collections import OrderedDict
    by_uuid: OrderedDict = OrderedDict()
    for r in rows:
        by_uuid.setdefault(r["uuid"], {"name": r["name"], "club": r["club"], "gender": r["gender"], "rankings": []})
        by_uuid[r["uuid"]]["rankings"].append(r)

    # If --results, scrape race data. Require exactly one match.
    if args.results:
        if len(by_uuid) > 1:
            print(f"Error: '{args.name}' matches {len(by_uuid)} riders. Use --club to disambiguate:")
            for uuid, info in by_uuid.items():
                print(f"  {info['name']} — {info['club']} ({uuid})")
            return

        uuid = next(iter(by_uuid))
        print(f"Fetching race results for {by_uuid[uuid]['name']}...")
        details = scrape_rider_details(uuid)
        if details:
            conn = get_connection()
            for rr in details["race_results"]:
                conn.execute(
                    """INSERT OR IGNORE INTO race_results
                       (rider_uuid, event_name, race_name, position,
                        points, race_date, year)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (uuid, rr["event_name"], rr["race_name"],
                     rr["position"], rr["points"], rr["race_date"], rr["year"]),
                )
            conn.commit()
            conn.close()
            print(f"  Stored {len(details['race_results'])} results.\n")

    # Display rider info
    for uuid, info in by_uuid.items():
        print(f"\n{'=' * 60}")
        print(f"  Rider: {info['name']}")
        print(f"  Club:  {info['club']}")
        print(f"  Gender: {info['gender']}")
        print(f"  UUID:  {uuid}")
        print(f"{'=' * 60}")
        print(f"{'Comp':>5s} {'Rank':>5s} {'Rider Cat':<8s} {'Pts':>5s}")
        print("-" * 30)
        for r in info["rankings"]:
            prov = "*" if r["is_provisional"] else " "
            print(
                f"{r['competition_category']:>5s} {r['rank']:>5d} "
                f"{r['rider_category']:<8s} {r['points']:>5s}{prov}"
            )
        print()

    # Show race results (use club for disambiguation if there are duplicates)
    results = get_rider_race_results(args.name, club=args.club)
    if results:
        print(f"  Race history ({len(results)} entries):")
        current_year = None
        for rr in results:
            if rr["year"] != current_year:
                current_year = rr["year"]
                print(f"\n  {'─' * 60}")
                print(f"  {current_year}")
                print(f"  {'Date':<15s} {'Event':<45s} {'Race':<30s} {'Pos':<5s} {'Pts':>5s}")
                print(f"  {'─' * 60}")
            print(
                f"  {rr['race_date']:<15s} {rr['event_name'][:43]:<45s}"
                f" {rr['race_name'][:28]:<30s} {rr['position']:<5s} {rr['points']:>5s}"
            )
    print()


def cmd_clubs(args):
    """List all clubs with rider count."""
    rows = list_clubs()
    if not rows:
        print("No clubs found.")
        return

    print(f"\n{'=' * 60}")
    print(f"  Clubs ({len(rows)} total)")
    print(f"{'=' * 60}")
    print(f"{'#':>4s} {'Club':<45s} {'Riders':>6s}")
    print("-" * 60)
    for i, row in enumerate(rows, 1):
        print(f"{i:>4d} {row['club'][:44]:<45s} {row['rider_count']:>6d}")
    print()


def cmd_stats(args):
    """Show database statistics."""
    stats = get_stats()
    print(f"\n{'=' * 50}")
    print("  Database Statistics")
    print(f"{'=' * 50}")
    print(f"  Total riders:       {stats['total_riders']}")
    print(f"  Total clubs:        {stats['total_clubs']}")
    print(f"  Total race results: {stats['total_race_results']}")
    if stats["last_scrape"]:
        print(f"  Last scraped:       {stats['last_scrape']}")
    print()
    print("  Riders per category:")
    for cat, count in stats["riders_per_category"].items():
        label = CATEGORY_LABELS.get(cat, cat)
        print(f"    {cat:>4s} ({label:<12s}): {count:>5d}")
    print()


# ── CLI ─────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Cycling Ireland Rankings — Scraper & Database"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # scrape
    p = sub.add_parser("scrape", help="Scrape all rankings into the database")
    p.add_argument("--delta", action="store_true", help="Skip categories scraped recently")
    p.add_argument(
        "--max-age", type=int,
        help="Max age in seconds for delta scrape (default: 1 hour)",
    )
    p.add_argument(
        "--with-results", action="store_true",
        help="Also scrape race results for all riders",
    )
    p.set_defaults(func=cmd_scrape)

    # rider-details
    p = sub.add_parser(
        "rider-details",
        help="Scrape detailed race results for one or all riders",
    )
    p.add_argument("--uuid", help="UUID of a specific rider")
    p.add_argument("--all", action="store_true", help="Scrape details for all riders")
    p.set_defaults(func=cmd_rider_details)

    # top
    p = sub.add_parser("top", help="Show top ranked riders")
    p.add_argument("--category", default="C1", help="Category (default: C1)")
    p.add_argument("--limit", type=int, default=10, help="Number of riders (default: 10)")
    p.add_argument("--gender", choices=["MALE", "FEMALE"], help="Filter by gender")
    p.set_defaults(func=cmd_top)

    # club
    p = sub.add_parser("club", help="Find riders by club name")
    p.add_argument("name", help="Club name (case-insensitive, partial match)")
    p.add_argument("--category", help="Filter by competition category (e.g. C1, C3)")
    p.add_argument("--gender", choices=["MALE", "FEMALE"], help="Filter by gender")
    p.set_defaults(func=cmd_club)

    # standings
    p = sub.add_parser("standings", help="Club standings — riders sorted by points")
    p.add_argument("name", help="Club name (case-insensitive, partial match)")
    p.add_argument("--gender", choices=["MALE", "FEMALE"], help="Filter by gender")
    p.set_defaults(func=cmd_standings)

    # rider
    p = sub.add_parser("rider", help="Look up a rider by name")
    p.add_argument("name", help="Rider name (case-insensitive, partial match)")
    p.add_argument("--club", help="Disambiguate by club name (partial match)")
    p.add_argument("--results", action="store_true", help="Fetch and show race results")
    p.set_defaults(func=cmd_rider)

    # clubs
    p = sub.add_parser("clubs", help="List all clubs with rider counts")
    p.set_defaults(func=cmd_clubs)

    # stats
    p = sub.add_parser("stats", help="Show database statistics")
    p.set_defaults(func=cmd_stats)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()