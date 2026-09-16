"""Query helpers for the Cycling Ireland Rankings database."""

from database import get_connection


def find_riders_by_club(club_name: str, category: str | None = None, gender: str | None = None):
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
    if gender:
        query += " AND r.gender = ?"
        params.append(gender.upper())

    query += " ORDER BY rk.competition_category, rk.rank"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return rows


def get_top_ranked(category: str, limit: int = 10, gender: str | None = None):
    """Get the top-N ranked riders in a competition category."""
    conn = get_connection()
    query = """
        SELECT r.name, r.club, r.gender,
               rk.rider_category, rk.rank, rk.points, rk.is_provisional
        FROM rankings rk
        JOIN riders r ON r.uuid = rk.rider_uuid
        WHERE rk.competition_category = ?
    """
    params = [category.upper()]
    if gender:
        query += " AND r.gender = ?"
        params.append(gender.upper())
    query += " ORDER BY rk.rank ASC LIMIT ?"
    params.append(limit)
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return rows


def get_club_rankings(min_riders: int = 1):
    """Rank clubs by points across riders. total_points is current ranking points,
    year_points is the sum of current-year race results (captures pre-upgrade points)."""
    conn = get_connection()
    current_year = conn.execute(
        "SELECT CAST(strftime('%Y', 'now') AS INTEGER)"
    ).fetchone()[0]
    rows = conn.execute(
        """
        SELECT r.club,
               COUNT(DISTINCT r.uuid) AS rider_count,
               SUM(CAST(rk.points AS INTEGER)) AS total_points,
               AVG(CAST(rk.points AS INTEGER)) AS avg_points,
               SUM(COALESCE((
                   SELECT SUM(CAST(rr.points AS INTEGER))
                   FROM race_results rr
                   WHERE rr.rider_uuid = r.uuid AND rr.year = ?
               ), 0)) AS year_points
        FROM riders r
        JOIN rankings rk ON r.uuid = rk.rider_uuid
        WHERE r.club IS NOT NULL AND r.club != ''
          AND (CAST(rk.points AS INTEGER) > 0
               OR COALESCE((SELECT SUM(CAST(rr.points AS INTEGER))
                   FROM race_results rr
                   WHERE rr.rider_uuid = r.uuid AND rr.year = ?), 0) > 0)
        GROUP BY r.club
        HAVING COUNT(DISTINCT r.uuid) >= ?
        ORDER BY year_points DESC, total_points DESC
        """,
        (current_year, current_year, min_riders),
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


def get_rider_details(name: str | None = None, club: str | None = None, uuid: str | None = None):
    """Get rider profile and current rankings by name or UUID, optionally filtered by club."""
    conn = get_connection()
    query = """
        SELECT DISTINCT r.uuid, r.name, r.club, r.gender,
               rk.competition_category, rk.rider_category,
               rk.rank, rk.points, rk.is_provisional
        FROM riders r
        JOIN rankings rk ON r.uuid = rk.rider_uuid
        WHERE 1=1
    """
    params: list = []
    if uuid:
        query += " AND r.uuid = ?"
        params.append(uuid)
    else:
        query += " AND r.name LIKE ?"
        params.append(f"%{name}%")
        if club:
            query += " AND r.club LIKE ?"
            params.append(f"%{club}%")
    query += " ORDER BY r.club, rk.competition_category"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return rows


def get_rider_race_results(name: str | None = None, club: str | None = None, uuid: str | None = None):
    """Get all race results for a rider by name or UUID, optionally filtered by club.
    Results sorted chronologically."""
    conn = get_connection()
    query = """
        SELECT rr.race_date, rr.event_name, rr.race_name,
               rr.position, rr.points, rr.year
        FROM race_results rr
        JOIN riders r ON r.uuid = rr.rider_uuid
        WHERE 1=1
    """
    params: list = []
    if uuid:
        query += " AND r.uuid = ?"
        params.append(uuid)
    else:
        query += " AND r.name LIKE ?"
        params.append(f"%{name}%")
        if club:
            query += " AND r.club LIKE ?"
            params.append(f"%{club}%")
    query += """
        ORDER BY rr.year ASC,
            CASE SUBSTR(rr.race_date, 4, 3)
                WHEN 'Jan' THEN 1 WHEN 'Feb' THEN 2 WHEN 'Mar' THEN 3
                WHEN 'Apr' THEN 4 WHEN 'May' THEN 5 WHEN 'Jun' THEN 6
                WHEN 'Jul' THEN 7 WHEN 'Aug' THEN 8 WHEN 'Sep' THEN 9
                WHEN 'Oct' THEN 10 WHEN 'Nov' THEN 11 WHEN 'Dec' THEN 12
            END ASC,
            CAST(SUBSTR(rr.race_date, 1, 2) AS INTEGER) ASC
    """
    rows = conn.execute(query, params).fetchall()
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


def get_club_standings(club_name: str, gender: str | None = None, show_zero: bool = False):
    """All riders in a club with their rankings, ordered by points descending.
    Mixes categories together; each row shows the competition category.
    year_points is the sum of current-year race results (captures pre-upgrade points)."""
    conn = get_connection()
    current_year = conn.execute(
        "SELECT CAST(strftime('%Y', 'now') AS INTEGER)"
    ).fetchone()[0]
    query = """
        SELECT r.uuid, r.name, r.club, r.gender,
               rk.competition_category, rk.rider_category,
               rk.rank, rk.points, rk.is_provisional,
               COALESCE((
                   SELECT SUM(CAST(rr.points AS INTEGER))
                   FROM race_results rr
                   WHERE rr.rider_uuid = r.uuid AND rr.year = ?
               ), 0) AS year_points
        FROM riders r
        JOIN rankings rk ON r.uuid = rk.rider_uuid
        WHERE r.club LIKE ?
    """
    params: list = [current_year]
    params.append(f"%{club_name}%")
    if not show_zero:
        query += (" AND (CAST(rk.points AS INTEGER) > 0"
                  " OR COALESCE((SELECT SUM(CAST(rr.points AS INTEGER))"
                  " FROM race_results rr"
                  " WHERE rr.rider_uuid = r.uuid AND rr.year = ?), 0) > 0)")
        params.append(current_year)
    if gender:
        query += " AND r.gender = ?"
        params.append(gender.upper())

    query += " ORDER BY year_points DESC, CAST(rk.points AS INTEGER) DESC, r.name ASC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return rows


def list_races(query: str = "", year: int | None = None, limit: int = 200):
    """List distinct races (event + race-name + year) with rider/points counts.
    Each race_name within an event is treated as a separate race."""
    conn = get_connection()
    sql = """
        SELECT event_name, race_name, year, MIN(race_date) AS race_date,
               COUNT(*) AS rider_count,
               SUM(CAST(points AS INTEGER)) AS total_points
        FROM race_results
        WHERE 1=1
    """
    params: list = []
    if query:
        sql += " AND (event_name LIKE ? OR race_name LIKE ?)"
        like = f"%{query}%"
        params += [like, like]
    if year:
        sql += " AND year = ?"
        params.append(year)
    sql += """
        GROUP BY event_name, race_name, year
        ORDER BY year DESC,
            CASE SUBSTR(MIN(race_date), 4, 3)
                WHEN 'Jan' THEN 1 WHEN 'Feb' THEN 2 WHEN 'Mar' THEN 3
                WHEN 'Apr' THEN 4 WHEN 'May' THEN 5 WHEN 'Jun' THEN 6
                WHEN 'Jul' THEN 7 WHEN 'Aug' THEN 8 WHEN 'Sep' THEN 9
                WHEN 'Oct' THEN 10 WHEN 'Nov' THEN 11 WHEN 'Dec' THEN 12
            END DESC,
            CAST(SUBSTR(MIN(race_date), 1, 2) AS INTEGER) DESC,
            event_name ASC, race_name ASC
        LIMIT ?
    """
    params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return rows


def get_race_riders(event_name: str, race_name: str, year: int):
    """Riders and results for a specific race."""
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT rr.race_date, rr.position, rr.points, rr.year,
               r.uuid, r.name, r.club, r.gender
        FROM race_results rr
        JOIN riders r ON r.uuid = rr.rider_uuid
        WHERE rr.event_name = ? AND rr.race_name = ? AND rr.year = ?
        ORDER BY CAST(rr.position AS INTEGER) ASC, r.name ASC
        """,
        (event_name, race_name, year),
    ).fetchall()
    conn.close()
    return rows