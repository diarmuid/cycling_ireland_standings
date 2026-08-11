"""Query helpers for the Cycling Ireland Rankings database."""

from database import get_connection


def find_riders_by_club(club_name: str, category: str | None = None):
    """Find all riders matching a club name (case-insensitive)."""
    conn = get_connection()
    query = """
        SELECT DISTINCT r.name, r.club, r.gender,
               rk.competition_category, rk.rider_category, rk.rank, rk.points,
               rk.is_provisional
        FROM riders r
        JOIN rankings rk ON r.uuid = rk.rider_uuid
        WHERE r.club LIKE ?
    """
    params = [f"%{club_name}%"]
    if category:
        query += " AND rk.competition_category = ?"
        params.append(category.upper())

    query += " ORDER BY rk.competition_category, rk.rank"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return rows


def get_top_ranked(category: str, limit: int = 10):
    """Get the top-N ranked riders in a competition category."""
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT r.name, r.club, r.gender,
               rk.rider_category, rk.rank, rk.points, rk.is_provisional
        FROM rankings rk
        JOIN riders r ON r.uuid = rk.rider_uuid
        WHERE rk.competition_category = ?
        ORDER BY rk.rank ASC
        LIMIT ?
        """,
        [category.upper(), limit],
    ).fetchall()
    conn.close()
    return rows


def get_stats():
    """Return summary statistics from the database."""
    conn = get_connection()
    stats = {}

    # Total riders
    stats["total_riders"] = conn.execute(
        "SELECT COUNT(*) FROM riders"
    ).fetchone()[0]

    # Riders per competition category
    category_counts = conn.execute(
        """
        SELECT competition_category, COUNT(*)
        FROM rankings
        GROUP BY competition_category
        ORDER BY competition_category
        """
    ).fetchall()
    stats["riders_per_category"] = {row[0]: row[1] for row in category_counts}

    # Total clubs
    stats["total_clubs"] = conn.execute(
        "SELECT COUNT(DISTINCT club) FROM riders WHERE club IS NOT NULL"
    ).fetchone()[0]

    # Last scrape time
    stats["last_scrape"] = conn.execute(
        "SELECT MAX(scraped_at) FROM scrape_meta"
    ).fetchone()[0]

    # Total race results (if scraped)
    stats["total_race_results"] = conn.execute(
        "SELECT COUNT(*) FROM race_results"
    ).fetchone()[0]

    conn.close()
    return stats


def get_rider_race_results(name: str):
    """Get all race results for a rider by name."""
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT rr.race_date, rr.event_name, rr.race_name,
               rr.position, rr.points, rr.year
        FROM race_results rr
        JOIN riders r ON r.uuid = rr.rider_uuid
        WHERE r.name LIKE ?
        ORDER BY rr.race_date DESC
        """,
        [f"%{name}%"],
    ).fetchall()
    conn.close()
    return rows


def list_clubs():
    """List all distinct clubs with rider count."""
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT club, COUNT(DISTINCT uuid) as rider_count
        FROM riders
        WHERE club IS NOT NULL AND club != ''
        GROUP BY club
        ORDER BY rider_count DESC
        """
    ).fetchall()
    conn.close()
    return rows


def get_rider_details(name: str):
    """Get rider profile and current rankings by name."""
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT DISTINCT r.uuid, r.name, r.club, r.gender,
               rk.competition_category, rk.rider_category,
               rk.rank, rk.points, rk.is_provisional
        FROM riders r
        JOIN rankings rk ON r.uuid = rk.rider_uuid
        WHERE r.name LIKE ?
        ORDER BY rk.competition_category
        """,
        [f"%{name}%"],
    ).fetchall()
    conn.close()
    return rows