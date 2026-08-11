# Cycling Ireland Standings

Scrapes Cycling Ireland national road rankings from the public website and stores them in a local SQLite database for querying.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Scrape the Data

Fetches rider rankings across all categories (C1, C2, C3, JC1–JC3, WMN, U16) and stores them in `rankings.db`:

```bash
python main.py scrape
```

## Commands

### Top ranked riders in a category

```bash
python main.py top --category C1 --limit 10
python main.py top --category WMN --limit 5
python main.py top --category U16
```

### Find riders by club

```bash
python main.py club "Burren Cycling Club"
python main.py club "Orwell" --category C1
```

### Look up a rider

```bash
python main.py rider "Daire Feeley"
python main.py rider "Paul Kennedy"
```

### List all clubs

```bash
python main.py clubs
```

### Scrape per-rider race history

```bash
python main.py rider-details --uuid <uuid>   # one rider
python main.py rider-details --all           # all riders (slow)
```

### Database stats

```bash
python main.py stats
```

## Data Source

Data comes from the Cycling Ireland membership portal's public API:

- `https://membership.cyclingireland.ie/api/ranking-table.html?rank={CATEGORY}`
- `https://membership.cyclingireland.ie/api/participant-info.html?uuid={UUID}`

No login or authentication required.

## Database Schema

| Table | Contents |
|---|---|
| `riders` | Rider profile (uuid, name, club, gender) |
| `rankings` | Current ranking per category (rank, points, rider category) |
| `race_results` | Per-rider race history (date, event, position, points) |
| `scrape_meta` | Scrape timestamps and counts |