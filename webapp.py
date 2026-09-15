#!/usr/bin/env python3
"""Web interface for Cycling Ireland Rankings."""

from bottle import route, run, request, template, redirect, static_file
from config import CATEGORIES, CATEGORY_LABELS
from database import get_connection
from queries import (
    find_riders_by_club,
    get_club_standings,
    get_rider_details,
    get_rider_race_results,
    get_stats,
    get_top_ranked,
    list_clubs,
)

HOST = "localhost"
PORT = 8090

BASE = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Cycling Ireland Rankings</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
</head>
<body class="bg-light">
  <nav class="navbar navbar-expand-lg navbar-dark bg-dark mb-4">
    <div class="container">
      <a class="navbar-brand fw-bold" href="/">CI Rankings</a>
      <div class="navbar-nav">
        <a class="nav-link" href="/standings">Standings</a>
        <a class="nav-link" href="/top">Top</a>
        <a class="nav-link" href="/rider">Rider</a>
        <a class="nav-link" href="/clubs">Clubs</a>
        <a class="nav-link" href="/stats">Stats</a>
      </div>
    </div>
  </nav>
  <div class="container">
    {{!body}}
  </div>
</body>
</html>
"""


def _page(body):
    return template(BASE, body=body)


def _prov(p):
    return " *" if p else ""


# ── Home ────────────────────────────────────────────────────────────────────


@route("/")
def home():
    stats = get_stats()
    cat_rows = ""
    for cat in CATEGORIES:
        count = stats["riders_per_category"].get(cat, 0)
        label = CATEGORY_LABELS.get(cat, cat)
        cat_rows += f"<tr><td>{cat}</td><td>{label}</td><td class='text-end'>{count}</td></tr>"

    body = f"""
    <div class="row g-4 mb-4">
      <div class="col-md-3"><div class="card text-center p-3"><h3>{stats['total_riders']}</h3><small class="text-muted">Riders</small></div></div>
      <div class="col-md-3"><div class="card text-center p-3"><h3>{stats['total_clubs']}</h3><small class="text-muted">Clubs</small></div></div>
      <div class="col-md-3"><div class="card text-center p-3"><h3>{stats['total_race_results']}</h3><small class="text-muted">Race Results</small></div></div>
      <div class="col-md-3"><div class="card text-center p-3"><h3>{stats.get('last_scrape', 'Never')}</h3><small class="text-muted">Last Scraped</small></div></div>
    </div>
    <div class="card">
      <div class="card-header"><strong>Riders per Category</strong></div>
      <div class="card-body p-0">
        <table class="table table-striped mb-0">
          <thead class="table-dark"><tr><th>Code</th><th>Category</th><th class='text-end'>Riders</th></tr></thead>
          <tbody>{cat_rows}</tbody>
        </table>
      </div>
    </div>
    """
    return _page(body)


# ── Standings ───────────────────────────────────────────────────────────────


@route("/standings", method="GET")
def standings_form():
    body = """
    <h4>Club Standings</h4>
    <form action="/standings" method="POST" class="row g-2 mb-3">
      <div class="col-auto"><input name="club" class="form-control" placeholder="Club name" required></div>
      <div class="col-auto">
        <select name="gender" class="form-select">
          <option value="">All genders</option>
          <option value="MALE">Male</option>
          <option value="FEMALE">Female</option>
        </select>
      </div>
      <div class="col-auto"><button class="btn btn-primary" type="submit">Go</button></div>
    </form>
    """
    return _page(body)


@route("/standings", method="POST")
def standings_results():
    club = request.forms.get("club", "")
    gender = request.forms.get("gender") or None
    rows = get_club_standings(club, gender=gender)
    if not rows:
        return _page(f'<div class="alert alert-warning">No riders found for "{club}".</div>')

    total_riders = len(set(r["name"] for r in rows))
    total_points = sum(int(r["points"]) for r in rows)
    avg_points = total_points / total_riders if total_riders else 0
    best_rank = min(r["rank"] for r in rows)

    trs = ""
    for r in rows:
        trs += f"<tr><td class='text-end'>{r['points']}{_prov(r['is_provisional'])}</td><td>{r['name']}</td><td>{r['rider_category']}</td><td>{r['competition_category']}</td><td>{r['gender']}</td><td class='text-end'>{r['rank']}</td></tr>"

    gender_tag = f" ({gender})" if gender else ""
    body = f"""
    <h4>Club Standings: {rows[0]['club']}{gender_tag}</h4>
    <div class="mb-3">
      <span class="badge bg-secondary me-2">{total_riders} riders</span>
      <span class="badge bg-secondary me-2">{total_points} total pts</span>
      <span class="badge bg-secondary me-2">Avg {avg_points:.0f}</span>
      <span class="badge bg-secondary">Best rank #{best_rank}</span>
    </div>
    <table class="table table-striped table-sm">
      <thead class="table-dark"><tr><th class='text-end'>Pts</th><th>Name</th><th>Rider Cat</th><th>Comp</th><th>Gender</th><th class='text-end'>Rank</th></tr></thead>
      <tbody>{trs}</tbody>
    </table>
    <a href="/standings" class="btn btn-outline-secondary btn-sm">&larr; Back</a>
    """
    return _page(body)


# ── Top Ranked ──────────────────────────────────────────────────────────────


@route("/top")
def top():
    category = request.query.get("category", "C1")
    limit = int(request.query.get("limit", 20))
    gender = request.query.get("gender") or None
    rows = get_top_ranked(category, limit=limit, gender=gender)

    cat_opts = "".join(
        f'<option value="{c}"{" selected" if c == category else ""}>{c} - {CATEGORY_LABELS.get(c, c)}</option>'
        for c in CATEGORIES
    )

    trs = ""
    for r in rows:
        trs += f"<tr><td class='text-end'>{r['rank']}</td><td>{r['name']}</td><td>{r['club'] or '-'}</td><td>{r['rider_category']}</td><td>{r['gender']}</td><td class='text-end'>{r['points']}{_prov(r['is_provisional'])}</td></tr>"

    body = f"""
    <h4>Top Ranked</h4>
    <form class="row g-2 mb-3">
      <div class="col-auto">
        <select name="category" class="form-select">{cat_opts}</select>
      </div>
      <div class="col-auto">
        <select name="gender" class="form-select">
          <option value="">All</option>
          <option value="MALE"{' selected' if gender == 'MALE' else ''}>Male</option>
          <option value="FEMALE"{' selected' if gender == 'FEMALE' else ''}>Female</option>
        </select>
      </div>
      <div class="col-auto">
        <input name="limit" type="number" value="{limit}" class="form-control" style="width:80px" min="1">
      </div>
      <div class="col-auto"><button class="btn btn-primary" type="submit">Go</button></div>
    </form>
    <table class="table table-striped table-sm">
      <thead class="table-dark"><tr><th class='text-end'>Rank</th><th>Name</th><th>Club</th><th>Rider Cat</th><th>Gender</th><th class='text-end'>Pts</th></tr></thead>
      <tbody>{trs}</tbody>
    </table>
    """
    return _page(body)


# ── Rider Search ────────────────────────────────────────────────────────────


@route("/rider")
def rider():
    name = request.query.get("name", "")
    club = request.query.get("club") or None

    body = """
    <h4>Search Rider</h4>
    <form class="row g-2 mb-3">
      <div class="col-auto"><input name="name" class="form-control" placeholder="Rider name" value="{name}"></div>
      <div class="col-auto"><input name="club" class="form-control" placeholder="Club (optional)"></div>
      <div class="col-auto"><button class="btn btn-primary" type="submit">Search</button></div>
    </form>
    """

    if name:
        rows = get_rider_details(name, club=club)
        if not rows:
            body += "<div class='alert alert-warning'>No rider found.</div>"
        else:
            by_uuid = {}
            for r in rows:
                by_uuid.setdefault(
                    r["uuid"],
                    {"name": r["name"], "club": r["club"], "gender": r["gender"], "rankings": []},
                )
                by_uuid[r["uuid"]]["rankings"].append(r)

            for uid, info in by_uuid.items():
                rtrs = ""
                for rk in info["rankings"]:
                    rtrs += f"<tr><td>{rk['competition_category']}</td><td class='text-end'>{rk['rank']}</td><td>{rk['rider_category']}</td><td class='text-end'>{rk['points']}{_prov(rk['is_provisional'])}</td></tr>"
                body += f"""
                <div class="card mb-3">
                  <div class="card-header"><strong>{info['name']}</strong> &mdash; {info['club'] or 'No club'} ({info['gender']})</div>
                  <div class="card-body p-0">
                    <table class="table table-striped mb-0 table-sm">
                      <thead class="table-dark"><tr><th>Comp</th><th class='text-end'>Rank</th><th>Rider Cat</th><th class='text-end'>Pts</th></tr></thead>
                      <tbody>{rtrs}</tbody>
                    </table>
                  </div>
                </div>
                """

                results = get_rider_race_results(name, club=club)
                if results:
                    rrs = ""
                    for rr in results:
                        rrs += f"<tr><td>{rr['race_date']}</td><td>{rr['event_name']}</td><td>{rr['race_name']}</td><td>{rr['position']}</td><td class='text-end'>{rr['points']}</td></tr>"
                    body += f"""
                    <h6 class="mt-2">Race History ({len(results)} results)</h6>
                    <table class="table table-sm table-striped">
                      <thead class="table-dark"><tr><th>Date</th><th>Event</th><th>Race</th><th>Pos</th><th class='text-end'>Pts</th></tr></thead>
                      <tbody>{rrs}</tbody>
                    </table>
                    """

    body = body.replace("{name}", name)
    return _page(body)


# ── Clubs ───────────────────────────────────────────────────────────────────


@route("/clubs")
def clubs():
    rows = list_clubs()
    trs = "".join(
        f'<tr><td>{i}</td><td><a href="/standings" onclick="document.forms[0].club.value=\'{r["club"]}\';document.forms[0].submit();return false">{r["club"]}</a></td><td class="text-end">{r["rider_count"]}</td></tr>'
        for i, r in enumerate(rows, 1)
    )

    body = f"""
    <h4>Clubs ({len(rows)} total)</h4>
    <form action="/standings" method="POST" style="display:none">
      <input name="club">
    </form>
    <table class="table table-striped table-sm">
      <thead class="table-dark"><tr><th>#</th><th>Club</th><th class='text-end'>Riders</th></tr></thead>
      <tbody>{trs}</tbody>
    </table>
    """
    return _page(body)


# ── Stats ────────���───────���──────────────────────────────────────────────────


@route("/stats")
def stats():
    s = get_stats()
    cat_rows = ""
    for cat in CATEGORIES:
        count = s["riders_per_category"].get(cat, 0)
        label = CATEGORY_LABELS.get(cat, cat)
        cat_rows += f"<tr><td>{cat}</td><td>{label}</td><td class='text-end'>{count}</td></tr>"

    body = f"""
    <h4>Database Statistics</h4>
    <table class="table table-sm" style="max-width:400px">
      <tr><td>Total Riders</td><td class='text-end fw-bold'>{s['total_riders']}</td></tr>
      <tr><td>Total Clubs</td><td class='text-end fw-bold'>{s['total_clubs']}</td></tr>
      <tr><td>Race Results</td><td class='text-end fw-bold'>{s['total_race_results']}</td></tr>
      <tr><td>Last Scraped</td><td class='text-end fw-bold'>{s.get('last_scrape', 'Never')}</td></tr>
    </table>
    <h6>Riders per Category</h6>
    <table class="table table-striped table-sm" style="max-width:400px">
      <thead class="table-dark"><tr><th>Code</th><th>Category</th><th class='text-end'>Riders</th></tr></thead>
      <tbody>{cat_rows}</tbody>
    </table>
    """
    return _page(body)


# ── Main ────────────────────────────────────────────────────────────────────


def main():
    print(f"Starting web app at http://{HOST}:{PORT}/")
    run(host=HOST, port=PORT, debug=True)


if __name__ == "__main__":
    main()
