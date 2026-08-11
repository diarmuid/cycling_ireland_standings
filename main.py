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
import time

from config import CATEGORIES, CATEGORY_LABELS
from database import get_connection, init_db
from queries import (
    find_riders_by_club,
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

    def progress(cat, count):
        print(f"  {cat:>4s} ({CATEGORY_LABELS.get(cat, cat)}): {count} riders")

    print("Fetching rankings from Cycling Ireland...")
    results = scrape_all_rankings(
        categories=CATEGORIES, delay=0.5, progress_callback=progress
    )

    total = 0
    for cat, riders in results.items():
        if not riders:
            continue

        for r in riders:
            # Upsert rider
            conn.execute(
                """INSERT OR IGNORE INTO riders (uuid, name, club, gender)
                   VALUES (?, ?, ?, ?)""",
                (r["uuid"], r["name"], r["club"], r["gender"]),
            )
            # Insert ranking entry
            conn.execute(
                """INSERT INTO rankings
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
            # Record scrape meta
        conn.execute(
            "INSERT INTO scrape_meta (category, rider_count) VALUES (?, ?)",
            (cat, len(riders)),
        )
        total += len(riders)

    conn.commit()
    conn.close()
    print(f"\nDone! {total} rankings stored across {len(results)} categories.")


# ── Rider Details ───────────────────────────────────────────────────────────


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

    count = 0
    for i, uuid in enumerate(uuids):
        details = scrape_rider_details(uuid)
        if not details:
            continue

        # Update rider info if we have more data
        if details["name"]:
            conn.execute(
                "UPDATE riders SET name=?, club=? WHERE uuid=?",
                (details["name"], details["club"], uuid),
            )

        # Insert race results
        for rr in details["race_results"]:
            conn.execute(
                """INSERT INTO race_results
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

        count += len(details["race_results"])

        if args.all and (i + 1) % 50 == 0:
            conn.commit()
            print(f"  {i + 1}/{len(uuids)} riders processed...")

    conn.commit()
    conn.close()
    print(f"\nDone! {count} race results stored.")


# ── Query commands ─────────────────────────────────────────────────────────


def cmd_top(args):
    """Show top ranked riders in a category."""
    rows = get_top_ranked(args.category, args.limit)
    if not rows:
        print(f"No rankings found for category '{args.category}'.")
        return

    label = CATEGORY_LABELS.get(args.category, args.category)
    print(f"\n{'=' * 70}")
    print(f"  Top {len(rows)} — {label}")
    print(f"{'=' * 70}")
    print(f"{'Rank':>5s} {'Name':<25s} {'Club':<30s} {'Cat':<8s} {'Pts':>5s}")
    print("-" * 75)
    for row in rows:
        prov = "*" if row["is_provisional"] else " "
        print(
            f"{row['rank']:>5d} {row['name']:<25s} {row['club']:<30s}"
            f" {row['rider_category']:<8s} {row['points']:>5s}{prov}"
        )
    print()


def cmd_club(args):
    """Find all riders from a given club."""
    rows = find_riders_by_club(args.name, args.category)
    if not rows:
        print(f"No riders found for club '{args.name}'.")
        return

    print(f"\n{'=' * 80}")
    print(f"  Riders matching club: {args.name}")
    if args.category:
        print(f"  Category: {args.category}")
    print(f"{'=' * 80}")
    print(
        f"{'Rank':>5s} {'Name':<25s} {'Club':<30s} "
        f"{'Comp':<5s} {'Rider Cat':<8s} {'Pts':>5s}"
    )
    print("-" * 80)
    for row in rows:
        prov = "*" if row["is_provisional"] else " "
        print(
            f"{row['rank']:>5d} {row['name']:<25s} {row['club']:<30s} "
            f"{row['competition_category']:<5s} {row['rider_category']:<8s} "
            f"{row['points']:>5s}{prov}"
        )
    print()


def cmd_rider(args):
    """Look up a rider by name."""
    rows = get_rider_details(args.name)
    if not rows:
        print(f"No rider found matching '{args.name}'.")
        return

    r = rows[0]
    print(f"\n{'=' * 60}")
    print(f"  Rider: {r['name']}")
    print(f"  Club:  {r['club']}")
    print(f"  Gender: {r['gender']}")
    print(f"{'=' * 60}")
    print(f"{'Comp':>5s} {'Rank':>5s} {'Rider Cat':<8s} {'Pts':>5s}")
    print("-" * 30)
    for row in rows:
        prov = "*" if row["is_provisional"] else " "
        print(
            f"{row['competition_category']:>5s} {row['rank']:>5d} "
            f"{row['rider_category']:<8s} {row['points']:>5s}{prov}"
        )
    print()

    # Show race results if available
    results = get_rider_race_results(args.name)
    if results:
        print(f"  Recent race results:")
        print(f"  {'Date':<15s} {'Event':<40s} {'Pos':<5s} {'Pts':>5s}")
        print("  " + "-" * 65)
        for rr in results[:10]:
            print(
                f"  {rr['race_date']:<15s} {rr['event_name'][:38]:<40s}"
                f" {rr['position']:<5s} {rr['points']:>5s}"
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
    p.set_defaults(func=cmd_top)

    # club
    p = sub.add_parser("club", help="Find riders by club name")
    p.add_argument("name", help="Club name (case-insensitive, partial match)")
    p.add_argument("--category", help="Filter by competition category (e.g. C1, C3)")
    p.set_defaults(func=cmd_club)

    # rider
    p = sub.add_parser("rider", help="Look up a rider by name")
    p.add_argument("name", help="Rider name (case-insensitive, partial match)")
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