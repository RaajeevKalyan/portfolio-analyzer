# CONTEXT.md - Portfolio Risk Analyzer

## 🎯 Quick Reference
**Paste this file with your requests to give me full context without reviewing all code.**

---

## Project Summary
A local, Docker-based Flask web app that aggregates portfolio data from CSV exports from multiple brokers (Merrill Lynch, Fidelity, Webull, Robinhood, Schwab), analyzes risk concentrations, identifies ETF/mutual fund overlaps, and tracks portfolio composition over time.

## Tech Stack
- **Backend**: Flask + Gunicorn + SQLAlchemy + SQLite (file-based, NOT a container) + Pandas (CSV parsing)
- **Frontend**: Bootstrap 5 + Chart.js + Vanilla JS
- **Infrastructure**: Docker (2 containers: nginx + Flask app)
- **Data Sources**: CSV files from brokers + mstarpy 8.0.3 (ETF/MF holdings)
- **Security**: File upload validation, OWASP hardening, TLS 1.2+

### Container Architecture (2 Containers)
1. **nginx container** - Reverse proxy, HTTPS termination, security headers
2. **Flask app container** - Application logic, Gunicorn WSGI server, CSV processing
3. **NOT a container** - SQLite database (just a file: `./data/portfolio.db`)

SQLite runs in-process within the Flask app. No separate database container needed.

## Implementation Status

### ✅ Phase 1: Complete
- CSV upload and parsing (Merrill Lynch format working)
- Database schema with all tables
- Dashboard showing broker cards with net worth
- ETF/Mutual Fund holdings resolution via mstarpy 8.0.3
- Background task for resolving underlying holdings
- Underlying holdings stored in JSON format in `Holding.underlying_holdings` field

### 🚧 Phase 2: In Progress
- Holdings aggregation table
- ETF/MF expansion view
- Overlap detection

### ⏳ Phase 3: Planned
- Risk analysis and charts
- Historical trends
- Snapshot management

## Core Features (Implemented)
1. ✅ Multi-broker CSV import (drag-and-drop or browse)
2. ✅ Portfolio aggregation and position consolidation across brokers
3. ✅ ETF/MF underlying holdings analysis (via mstarpy)
4. ⏳ Risk analysis (in progress):
   - Stock concentration (>20% = red flag)
   - ETF/MF overlap (>70% = high risk)
   - Sector concentration
   - Geographic exposure
5. ⏳ Historical trend tracking (user-configurable snapshot retention, default 25)
6. ⏳ Data management (clear history, reset all data)
7. ❌ Light/dark theme toggle (not yet implemented)
8. ✅ Broker-specific CSV parsers for format variations

## Architecture Decisions

### Database Schema
- **UserSettings**: Theme preference, snapshot retention limit
- **BrokerAccount**: Broker name, account identifier, last upload timestamp
- **PortfolioSnapshot**: Point-in-time portfolio state per broker
- **AggregateSnapshot**: Combined snapshot across all brokers
- **Holding**: Individual positions (stocks, ETFs, MFs)
  - `underlying_holdings`: JSON field storing resolved ETF/MF constituents
  - `underlying_parsed`: Boolean flag indicating if resolution attempted
- **UnderlyingHolding**: (FUTURE) Resolved ETF/MF constituents aggregated across portfolio
- **RiskMetrics**: (FUTURE) Calculated risk indicators for aggregate portfolio

### Key Workflows
1. **First-time setup**: Dashboard → Upload CSV to broker card → Parse & store → Show net worth
2. **Manual refresh**: Download new CSV from broker → Upload to card → Create new snapshot → Background task resolves ETF/MF holdings
3. **Holdings resolution**: Background thread calls mstarpy → Fetches top holdings → Stores as JSON in `Holding.underlying_holdings`
4. **Historical view**: (TODO) Fetch last N aggregate snapshots → Build time-series → Render charts
5. **Data cleanup**: (TODO) Confirm → Delete old snapshots OR reset entire database

### Security Approach
- **File Uploads**: Size limits (10MB), extension validation (.csv only), content verification
- **Network**: HTTPS only (port 80 redirects), TLS 1.2+, strong ciphers
- **Application**: CSRF protection, input validation, SQL injection prevention via ORM
- **Infrastructure**: nginx with OWASP Top 10 hardening, security headers, rate limiting

## File Organization

```
portfolio-analyzer/
├── docker-compose.yml          # Service orchestration
├── Dockerfile                  # Flask app container
├── requirements.txt            # Python dependencies (includes mstarpy==8.0.3)
├── .env                        # Secrets (gitignored)
├── nginx/
│   ├── Dockerfile              # nginx container
│   ├── nginx.conf              # Proxy config with security
│   └── ssl/                    # Self-signed certificates
├── app/
│   ├── main.py                 # Flask entry point, route registration
│   ├── config.py               # Configuration
│   ├── models.py               # SQLAlchemy models
│   ├── database.py             # DB connection & session management
│   ├── routes/
│   │   ├── __init__.py         # Route imports
│   │   └── upload.py           # CSV upload handling with background resolver
│   ├── services/
│   │   ├── csv_parser_base.py          # Abstract CSV parser
│   │   ├── merrill_csv_parser.py       # Merrill format (IMPLEMENTED)
│   │   ├── holdings_resolver.py        # ETF/MF resolution via mstarpy 8.0.3
│   │   ├── fidelity_csv_parser.py      # Fidelity format (TODO)
│   │   ├── webull_csv_parser.py        # Webull format (TODO)
│   │   ├── robinhood_csv_parser.py     # Robinhood format (TODO)
│   │   └── schwab_csv_parser.py        # Schwab format (TODO)
│   ├── utils/                  # Helpers
│   ├── static/                 # CSS, JS, images
│   └── templates/
│       └── dashboard.html      # Main dashboard with broker cards
├── data/                       # SQLite database (gitignored)
├── uploads/                    # Uploaded CSV files (gitignored)
├── logs/                       # Application logs (gitignored)
└── test_holdings_resolver.py  # CLI testing tool for resolver
```

## Implemented Routes

### Main Application (`app/main.py`)
- `GET /` - Dashboard showing broker cards and net worth
- `GET /health` - Health check endpoint

### Upload Blueprint (`app/routes/upload.py`)
- `POST /upload` - Handle CSV file upload
  - Validates file and broker
  - Parses CSV using broker-specific parser
  - Stores snapshot and holdings in database
  - Triggers background task to resolve ETF/MF holdings
  - Returns JSON response with snapshot details

## ETF/MF Holdings Resolution

### mstarpy 8.0.3 Integration
The holdings resolver uses mstarpy to fetch underlying holdings for ETFs and mutual funds.

**Initialization:**
```python
fund = mstarpy.Funds(term=symbol, pageSize=1)
holdings_df = fund.holdings()  # Returns pandas DataFrame
```

**DataFrame Structure:**
- 64 rows (holdings) × 57 columns
- Key columns: `secId`, `ticker`, `securityName`, `weighting`
- `weighting` is percentage (e.g., 3.70392 = 3.70%)

**Process:**
1. Upload CSV with ETF/MF → Stored as `Holding` with `underlying_parsed=False`
2. Background thread calls `resolve_snapshot_holdings(snapshot_id)`
3. For each ETF/MF: `mstarpy.Funds(term=symbol).holdings()`
4. Parse DataFrame → Extract symbol, name, weight
5. Calculate estimated value: `weight × total_value`
6. Store as JSON in `Holding.underlying_holdings`
7. Set `underlying_parsed=True`

**Example Data:**
```json
[
  {
    "symbol": "NVDA",
    "name": "NVIDIA Corp",
    "weight": 0.037039,
    "value": 137.76,
    "shares": null
  },
  ...
]
```

### Resolver Functions
- `HoldingsResolver.resolve_holding()` - Resolve single ETF/MF
- `resolve_snapshot_holdings(snapshot_id)` - Resolve all ETF/MFs in a snapshot
- `resolve_all_unresolved_holdings()` - Backfill all unresolved holdings

### Testing
```bash
# Test single symbol
docker-compose exec app python test_holdings_resolver.py DBMAX mutual_fund 3721.29

# Resolve all unresolved
docker-compose exec app python test_holdings_resolver.py --resolve-all

# Resolve specific snapshot
docker-compose exec app python test_holdings_resolver.py --snapshot 1
```

## Merrill Lynch CSV Format

Merrill CSVs have a complex multi-section format:

### Structure:
1. **Account summary** (skip) - Single quotes or comma-prefixed lines
2. **Empty line with `""`**
3. **Holdings header row** - Starts with `"Symbol "`
4. **Holdings data rows**
5. **Footer section** - "Balances", "Total", "Cash balance", etc.

### Parser Logic:
1. Find header row containing "Symbol", "Description", "Quantity"
2. Extract data rows until footer markers ("Balances", "Total", etc.)
3. Filter out empty lines and comma-only lines
4. Parse holdings with flexible column matching
5. Handle Merrill's inconsistent number formats (e.g., `$14,80.76`)

### Example:
```csv
, "IRRA-Edge 43X-40L72" ,"Value" ,"Day's Value Change"
"" ,"$10,480.76" ,"$0.00 0.00%"

""
"Symbol " ,"Description" ,"Quantity" ,"Value" ,"Price"
"AMD" ,"ADVANCED MICRO DEVICES" ,"57" ,"$14,801.76" ,"$259.68"
"DBMAX" ,"BNY MELLON SMALL/MID CAP" ,"171.567" ,"$3,721.29" ,"$21.69"
""
```

## UI Layout

### Dashboard (Implemented)
```
┌─────────────────────────────────────────────────────────────┐
│ Navbar: Logo | Portfolio Risk Analyzer | [Theme]            │
├─────────────────────────────────────────────────────────────┤
│ Total Net Worth: $18,523.05 | Last Updated: Jan 26          │
│                                                               │
│ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐        │
│ │ Merrill  │ │ Fidelity │ │  Webull  │ │Robinhood │        │
│ │$18,523   │ │   [Upload │ │  [Upload │ │  [Upload │        │
│ │2 pos     │ │    Zone]  │ │   Zone]  │ │   Zone]  │        │
│ │[Update]  │ │           │ │          │ │          │        │
│ └──────────┘ └──────────┘ └──────────┘ └──────────┘        │
│ ┌──────────┐                                                 │
│ │  Schwab  │                                                 │
│ │ [Upload  │                                                 │
│ │  Zone]   │                                                 │
│ └──────────┘                                                 │
└─────────────────────────────────────────────────────────────┘
```

### Holdings Table (Phase 2 - In Progress)
Will show aggregated holdings with:
- Same symbol grouped across brokers
- Broker breakdown as sub-rows
- ETF/MF chevron for expansion
- Underlying holdings display
- Overlap warnings

### Charts (Phase 3 - Planned)
- Chart.js for all visualizations
- Donut (portfolio allocation)
- Pie (concentrations)
- Line (trends)
- Bar (sectors/geography)

## Critical Constraints

### DO NOT CHANGE:
1. **Single-user mode**: No multi-user auth system
2. **Manual refresh only**: No automatic data pulls  
3. **CSV-only approach**: No OAuth integration (can add later)
4. **Desktop-only UI**: No mobile responsive requirements
5. **Localhost deployment**: No public cloud features
6. **SQLite database**: No migration to other databases
7. **HTTPS only**: Port 80 must redirect to 443
8. **Supported brokers**: Merrill Lynch (working), Fidelity, Webull, Robinhood, Schwab (TODO)

### MUST FOLLOW:
1. **OWASP Top 10**: All mitigations documented in SECURITY_SPEC.md
2. **nginx hardening**: Security headers, TLS 1.2+, strong ciphers
3. **Input validation**: All user inputs validated/sanitized (especially CSV files)
4. **CSRF protection**: All state-changing operations protected
5. **File upload security**: Size limits, extension validation, content verification
6. **No browser storage**: localStorage/sessionStorage not used (artifacts limitation)
7. **mstarpy 8.0.3 API**: Use `Funds(term=symbol, pageSize=1)` - NO `country` parameter

## Common Issues & Solutions

### Docker Image Caching
**Problem**: Code changes not picked up after rebuild

**Solution**:
```bash
docker-compose down
docker-compose build --no-cache app
docker-compose up -d
```

### Holdings Not Resolving
**Problem**: ETF/MF marked as `underlying_parsed=True` but no data

**Solution**:
```bash
# Check mstarpy can fetch data
docker-compose exec app python -c "
import mstarpy
fund = mstarpy.Funds(term='VTI')
print(fund.holdings().head())
"

# Reset parsed flags
docker-compose exec app python -c "
from app.database import db_session
from app.models import Holding
with db_session() as session:
    holdings = session.query(Holding).filter(
        Holding.asset_type.in_(['etf', 'mutual_fund'])
    ).all()
    for h in holdings:
        h.underlying_parsed = False
"

# Re-run resolver
docker-compose exec app python -c "
from app.services.holdings_resolver import resolve_all_unresolved_holdings
print(resolve_all_unresolved_holdings())
"
```

### F-String Syntax Errors
**Problem**: Nested f-strings with dictionary access cause syntax errors

**Wrong**:
```python
f"Data: {[f\"{x['key']}\" for x in items]}"  # SyntaxError
```

**Correct**:
```python
# Move logic outside f-string
data = [x['key'] for x in items]
f"Data: {data}"
```

## Development Workflow

### Making Code Changes
1. Modify code in `app/` directory
2. Test syntax: `python3 -m py_compile <file>`
3. Rebuild: `docker-compose down && docker-compose up -d --build`
4. Check logs: `docker-compose logs -f app`
5. If OK, commit changes

### Database Schema Changes
1. Modify models in `app/models.py`
2. Database auto-creates tables on startup via `init_db()`
3. For major changes, may need to delete `data/portfolio.db` and restart
4. Test data integrity

### Debugging
- **App errors**: `docker-compose logs app`
- **Import errors**: `docker-compose run --rm app python -c "from app.main import app"`
- **Database issues**: `docker-compose exec app python -c "from app.database import db_session; ..."`
- **Holdings resolver**: `docker-compose exec app python test_holdings_resolver.py --resolve-all`

## Version Information
- Python: 3.11
- Flask: 3.0.0
- SQLAlchemy: 2.0.23
- Bootstrap: 5.3
- Chart.js: 4.x
- nginx: 1.25
- mstarpy: 8.0.3
- pandas: Latest
- Gunicorn: Latest

## Quick Commands

```bash
# Start services
docker-compose up -d

# Rebuild without cache (when code changes don't work)
docker-compose down
docker-compose build --no-cache app
docker-compose up -d

# View logs
docker-compose logs -f app

# Stop services
docker-compose down

# Backup database
cp data/portfolio.db backups/portfolio_$(date +%Y%m%d).db

# Reset database (delete and restart)
docker-compose down
rm -f data/portfolio.db
docker-compose up -d

# Test holdings resolver
docker-compose exec app python test_holdings_resolver.py VTI etf 10000
docker-compose exec app python test_holdings_resolver.py --resolve-all

# Check database contents
docker-compose exec app python -c "
from app.database import db_session
from app.models import Holding
with db_session() as session:
    holdings = session.query(Holding).all()
    for h in holdings:
        print(f'{h.symbol}: {h.asset_type}, parsed={h.underlying_parsed}')
"

# Access database directly
docker-compose exec app sqlite3 /app/data/portfolio.db

# Check SSL configuration
openssl s_client -connect localhost:443 -servername localhost
```

## Next Steps (Phase 2)

1. Create holdings aggregation route (`/holdings`)
2. Build aggregation service to combine holdings across brokers
3. Create holdings table UI with:
   - Grouped by symbol
   - Broker breakdown
   - ETF/MF expansion chevron
   - Underlying holdings display
   - Overlap detection
4. Add filtering and sorting

## Repository Structure
- **Bitbucket**: https://bitbucket.org/raajeev/portfolio-analyzer
- **Main branch**: Contains all working code
- **Docker containers**: portfolio-app (Flask), portfolio-nginx (reverse proxy)

---

## 📌 Remember
- This is a **single-user**, **localhost-only** tool
- Security is critical: File uploads must be validated, data must be protected
- Manual CSV upload only: No automatic data pulls
- Desktop browsers only: No mobile responsive design needed
- Always rebuild with `--no-cache` when debugging code changes
- mstarpy 8.0.3 API uses `Funds(term=symbol)` - NO `country` parameter
- F-strings with nested quotes need special handling
- Background tasks run in separate threads for ETF/MF resolution