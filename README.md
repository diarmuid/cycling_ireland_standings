# Cycling Ireland Standings

Scrapes Cycling Ireland national road rankings from the public API and stores them in a local SQLite database for querying.

- **3,312 riders** across 8 competition categories
- **328 clubs** represented
- Per-rider race history (individual results per event)

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Getting Data

### Step 1: Scrape the rankings (all riders, all categories)

```bash
python main.py scrape
```

This fetches every rider across C1, C2, C3, JC1–JC3, WMN, and U16. It's fast — only 8 API calls.

### Step 2: Fetch race results for a rider

Race history isn't included in the initial scrape. Fetch it on demand:

```bash
# Fetch and display in one step
python main.py rider "Daire Feeley" --results

# If the name is ambiguous, specify the club
python main.py rider "Mark Kelly" --club Orwell --results

# Or fetch by UUID directly
python main.py rider-details --uuid 800892c4-b9bb-11ea-961a-021544c7365a

# Fetch results for ALL riders (slow — ~2,800 API calls)
python main.py rider-details --all
```

## Queries

### Look up a rider

```bash
python main.py rider "Daire Feeley"

# Disambiguate duplicate names
python main.py rider "Mark Kelly" --club Orwell

# Include race history (fetches from API if not already stored)
python main.py rider "Daire Feeley" --results
python main.py rider "Luke Keaney" --club Orwell --results
```

Output: rider profile, current rankings per category, and all race results grouped by year in date order.

### Top ranked riders

```bash
python main.py top --category C1 --limit 10
python main.py top --category WMN
python main.py top --category U16 --limit 5
python main.py top --category C3 --gender FEMALE
```

### Find riders by club

```bash
python main.py club "Orwell Wheelers Cycling Club"
python main.py club "Burren"                          # partial name match
python main.py club "Orwell" --category C1            # filter by category
python main.py club "Orwell" --gender FEMALE          # filter by gender
python main.py club "Orwell" --category C3 --gender MALE
```

### List all clubs

```bash
python main.py clubs
```

Shows every club with its rider count, sorted by size.

### Database statistics

```bash
python main.py stats
```

Shows total riders, clubs, results, and a breakdown per competition category.

## Database

The database file is `rankings.db` (SQLite). You can also query it directly:

```bash
sqlite3 rankings.db "SELECT name, club, gender FROM riders WHERE club LIKE '%Orwell%';"
sqlite3 rankings.db "SELECT COUNT(*) FROM riders;"
```

### Schema

| Table | Contents | Key fields |
|---|---|---|
| `riders` | Rider profile | uuid, name, club, gender |
| `rankings` | Current ranking per category | rider_uuid, competition_category, rank, points, rider_category |
| `race_results` | Per-rider race history | rider_uuid, race_date, event_name, race_name, position, points, year |
| `scrape_meta` | Scrape timestamps | category, rider_count, scraped_at |

### Competition categories

| Code | Label |
|---|---|
| C1 | Category 1 (top amateur / elite) |
| C2 | Category 2 |
| C3 | Category 3 (entry level) |
| JC1–JC3 | Junior categories 1–3 |
| WMN | Women |
| U16 | Under 16 |

## Data Source

The data comes from the Cycling Ireland membership portal's public API. No login required.

- Rankings: `https://membership.cyclingireland.ie/api/ranking-table.html?rank={CATEGORY}`
- Rider details: `https://membership.cyclingireland.ie/api/participant-info.html?uuid={UUID}`