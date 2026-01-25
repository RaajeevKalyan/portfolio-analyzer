### Aggregate Snapshot (NEW)
```python
class AggregateSnapshot(Model):
    id: int (PK)
    snapshot_date: datetime
    total_value: decimal (sum across all brokers)
    total_positions: int (sum across all brokers)
    created_at: datetime
    
    # Relationships
    portfolio_snapshots: List[PortfolioSnapshot] (via join table)
    risk_metrics: RiskMetrics
```# Architecture - Portfolio Risk Analyzer

## System Architecture Diagram

**Note**: This architecture uses **2 Docker containers** (nginx + Flask app). SQLite is NOT a container - it's a database file accessed via volume mount.

```
┌─────────────────────────────────────────────────────────────┐
│                         Docker Host                          │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │                    Docker Compose                       │ │
│  │                                                          │ │
│  │  ┌──────────────┐         ┌─────────────────────────┐  │ │
│  │  │ CONTAINER 1  │────────▶│    CONTAINER 2          │  │ │
│  │  │    nginx     │  proxy  │    Flask App            │  │ │
│  │  │  (Port 443)  │         │  (Gunicorn :5000)       │  │ │
│  │  │              │         │                         │  │ │
│  │  │  • TLS Term  │         │  • Routes/Controllers   │  │ │
│  │  │  • OWASP     │         │  • Business Logic       │  │ │
│  │  │  • Headers   │         │  • OAuth Handlers       │  │ │
│  │  └──────────────┘         │  • Data Processing      │  │ │
│  │         │                 └───────────┬─────────────┘  │ │
│  │         │                             │                │ │
│  │         │                             │ File I/O       │ │
│  │         │                             ▼                │ │
│  │         │                 ┌─────────────────────────┐  │ │
│  │         │                 │   NOT A CONTAINER       │  │ │
│  │         │                 │   SQLite Database File  │  │ │
│  │         │                 │   (Volume Mount)        │  │ │
│  │         │                 │                         │  │ │
│  │         │                 │  portfolio.db           │  │ │
│  │         │                 │  • Users                │  │ │
│  │         │                 │  • Broker Credentials   │  │ │
│  │         │                 │  • Portfolio Snapshots  │  │ │
│  │         │                 │  • Holdings             │  │ │
│  │         │                 │  • Risk Metrics         │  │ │
│  │         │                 └─────────────────────────┘  │ │
│  │         │                                              │ │
│  │         ▼                           ▲                  │ │
│  │  ┌──────────────────────────────────┼────────────────┐ │ │
│  │  │            Volume Mounts (Host Files)             │ │ │
│  │  │  • ./data/portfolio.db    →  /app/data/          │ │ │
│  │  │  • ./nginx/ssl/cert.pem   →  /etc/nginx/ssl/     │ │ │
│  │  │  • ./nginx/ssl/key.pem    →  /etc/nginx/ssl/     │ │ │
│  │  │  • ./logs/                →  /app/logs/          │ │ │
│  │  └───────────────────────────────────────────────────┘ │ │
│  └──────────────────────────────────────────────────────┘ │
│                                                              │
│                           ▲                                  │
│                           │                                  │
└───────────────────────────┼──────────────────────────────────┘
                            │
                    HTTPS (Port 443)
                            │
                            │
                    ┌───────┴────────┐
                    │   Browser      │
                    │  (localhost)   │
                    └────────────────┘
```

### Container Count: 2 (Not 3)
- **Container 1**: nginx (reverse proxy, TLS termination)
- **Container 2**: Flask app (application logic, Gunicorn WSGI server)
- **NOT a Container**: SQLite database (just a file on disk, accessed via volume mount)

## Application Structure

```
portfolio-analyzer/
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── .env.example
├── README.md
├── nginx/
│   ├── Dockerfile
│   ├── nginx.conf
│   └── ssl/
│       ├── generate_cert.sh
│       ├── cert.pem (generated)
│       └── key.pem (generated)
├── app/
│   ├── __init__.py
│   ├── config.py
│   ├── models.py
│   ├── database.py
│   ├── main.py (Flask app entry)
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── dashboard.py
│   │   ├── upload.py (CSV upload handling)
│   │   ├── portfolio.py
│   │   ├── settings.py
│   │   └── api.py (AJAX endpoints)
│   ├── services/
│   │   ├── __init__.py
│   │   ├── csv_parser_base.py
│   │   ├── merrill_csv_parser.py
│   │   ├── fidelity_csv_parser.py
│   │   ├── webull_csv_parser.py
│   │   ├── robinhood_csv_parser.py
│   │   ├── schwab_csv_parser.py
│   │   ├── holdings_parser.py (mstarpy + fallback)
│   │   ├── portfolio_aggregator.py
│   │   └── risk_analyzer.py
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── validators.py
│   │   └── helpers.py
│   ├── static/
│   │   ├── css/
│   │   │   ├── main.css
│   │   │   ├── light-theme.css
│   │   │   └── dark-theme.css
│   │   ├── js/
│   │   │   ├── main.js
│   │   │   ├── charts.js
│   │   │   ├── theme-toggle.js
│   │   │   └── dashboard.js
│   │   └── img/
│   │       └── broker-logos/
│   └── templates/
│       ├── base.html
│       ├── setup/
│       │   ├── welcome.html
│       │   └── broker_connect.html
│       ├── dashboard.html
│       ├── portfolio.html
│       ├── risk_analysis.html
│       ├── historical.html
│       ├── settings.html
│       └── components/
│           ├── navbar.html
│           ├── risk_card.html
│           └── chart_container.html
└── scripts/
    ├── holdings_scraper.py (fallback for mstarpy)
    └── init_db.py
```

## Data Models

### User Settings
```python
class UserSettings(Model):
    id: int (PK)
    snapshot_retention_limit: int (default: 25)
    theme_preference: str ('light' | 'dark')
    created_at: datetime
    updated_at: datetime
```

### Broker Account
```python
class BrokerAccount(Model):
    id: int (PK)
    broker_name: str ('merrill' | 'fidelity' | 'webull' | 'robinhood' | 'schwab')
    account_number_last4: str (extracted from CSV, optional)
    account_nickname: str (user-defined, optional)
    last_uploaded_at: datetime
    last_csv_filename: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
```

### Portfolio Snapshot
```python
class PortfolioSnapshot(Model):
    id: int (PK)
    broker_account_id: int (FK -> BrokerAccount)
    snapshot_date: datetime
    total_value: decimal
    total_positions: int
    upload_source: str ('csv_upload')
    csv_filename: str
    created_at: datetime
    
    # Relationships
    holdings: List[Holding]
    # Note: RiskMetrics calculated across ALL broker snapshots, not per-broker
```

### Holding
```python
class Holding(Model):
    id: int (PK)
    snapshot_id: int (FK -> PortfolioSnapshot)
    broker_name: str
    symbol: str
    name: str
    quantity: decimal
    price: decimal
    total_value: decimal
    asset_type: str ('stock' | 'etf' | 'mutual_fund' | 'bond' | 'cash')
    account_type: str ('taxable' | 'ira' | '401k' | 'roth')
    
    # For ETFs/MFs - store underlying holdings
    underlying_holdings: JSON (nullable)
    # [{"symbol": "AAPL", "weight": 0.05, "value": 1000}, ...]
```

### UnderlyingHolding (Resolved)
```python
class UnderlyingHolding(Model):
    id: int (PK)
    snapshot_id: int (FK -> PortfolioSnapshot)
    symbol: str
    name: str
    total_value: decimal (aggregated across all sources)
    percentage_of_portfolio: decimal
    sector: str
    geography: str
    
    # Source tracking
    sources: JSON
    # [{"from_holding_id": 123, "weight": 0.5, "value": 500}, ...]
```

### RiskMetrics
```python
class RiskMetrics(Model):
    id: int (PK)
    snapshot_id: int (FK -> PortfolioSnapshot)
    
    # Stock concentration
    concentrated_stocks: JSON
    # [{"symbol": "AAPL", "percentage": 0.25, "value": 50000}, ...]
    
    # ETF/MF overlap
    overlapping_funds: JSON
    # [{"funds": ["VTI", "ITOT"], "overlap_pct": 0.85, "overlapping_value": 30000}, ...]
    
    # Sector concentration
    sector_breakdown: JSON
    # {"Technology": 0.40, "Healthcare": 0.20, ...}
    
    # Geographic exposure
    geography_breakdown: JSON
    # {"US": 0.70, "International Developed": 0.20, "Emerging": 0.10}
    
    created_at: datetime
```

## Component Responsibilities

### Routes Layer
- **dashboard.py**: Main dashboard view, broker cards display, aggregate net worth
- **upload.py**: CSV file upload handling, validation, parser routing
- **portfolio.py**: Detailed holdings view, position tables
- **settings.py**: User preferences, broker management, data cleanup
- **api.py**: AJAX endpoints for refresh, chart data, risk calculations

### Services Layer

#### CSV Parser Services
- **csv_parser_base.py**: Abstract base class defining CSV parser interface
  - validate_csv(file) - Check format, headers
  - parse_csv(file) - Extract positions
  - extract_account_number(data) - Get account identifier
  
- **merrill_csv_parser.py**: Parses Merrill Lynch CSV format
- **fidelity_csv_parser.py**: Parses Fidelity CSV format
- **webull_csv_parser.py**: Parses Webull CSV format
- **robinhood_csv_parser.py**: Parses Robinhood CSV format
- **schwab_csv_parser.py**: Parses Schwab CSV format

Each parser handles:
- Column name variations
- Number formatting (commas, currency symbols)
- Date parsing
- Account number extraction
- Symbol normalization

#### Analysis Services
- **holdings_parser.py**: 
  - Fetches ETF/MF holdings via mstarpy
  - Falls back to custom scraper if needed
  - Caches results to avoid redundant API calls
  
- **portfolio_aggregator.py**:
  - Combines positions across all brokers
  - Resolves ETF/MF to underlying stocks
  - Calculates aggregate positions by symbol
  - Handles duplicate detection (same stock across brokers)
  
- **risk_analyzer.py**:
  - Calculates stock concentration percentages
  - Detects ETF/MF overlaps (set intersection on holdings)
  - Computes sector breakdown (from holdings metadata)
  - Computes geographic exposure
  - Generates risk flags and alerts

### Utils Layer
- **validators.py**: Input validation, data sanitization, CSV format validation
- **helpers.py**: Date formatting, number formatting, common utilities, file size checks

## Data Flow

### Initial Setup Flow
```
1. User lands on /dashboard
2. Sees 5 broker cards in "No data yet" state
3. Downloads CSV from broker website (external to app)
4. Drags CSV file onto Merrill Lynch broker card OR clicks Browse
5. POST to /upload with file and broker_name='merrill'
6. Server validates file (size, extension, format)
7. Parse CSV using MerrillCSVParser
8. Create or update BrokerAccount for Merrill
9. Create new PortfolioSnapshot for this broker
10. Parse ETF/MF holdings (mstarpy)
11. Store holdings in database
12. If multiple brokers have data, create/update AggregateSnapshot
13. Calculate risk metrics for aggregate portfolio
14. Return success + updated broker card data (net worth, position count)
15. Frontend updates card to "Has Data" state
16. User repeats for other brokers as desired
```

### Manual Refresh Flow (Per Broker)
```
1. User downloads new CSV from Merrill website
2. Drags onto Merrill card
3. POST to /upload with file and broker_name='merrill'
4. Server validates file
5. Parse CSV using MerrillCSVParser
6. Create new PortfolioSnapshot for Merrill (broker_account_id)
7. For each holding:
   a. If ETF/MF, fetch underlying holdings
   b. Store in holdings table
8. Delete old snapshots beyond retention limit (per broker)
9. Recalculate AggregateSnapshot (combines latest from all brokers)
10. Recalculate risk metrics for aggregate portfolio
11. Return updated data as JSON
12. Frontend updates Merrill card + aggregate displays
```

### Historical Trend Flow
```
1. User navigates to /historical
2. Fetch last N snapshots (per retention limit)
3. For each snapshot:
   a. Get top concentrated stocks
   b. Get overlap data
   c. Get sector/geography breakdown
4. Prepare time-series data for charting
5. Render Chart.js line/area charts showing:
   - Stock concentration over time
   - Sector drift
   - Geographic allocation changes
```

### Data Cleanup Flow
```
1. User clicks "Clear Historical Snapshots"
2. Confirmation modal appears
3. User confirms
4. DELETE snapshots older than most recent
5. Keep most recent snapshot only
6. Cascade delete associated holdings and risk_metrics

OR

1. User clicks "Reset All Data"
2. First confirmation modal
3. Second confirmation with type-to-confirm
4. DELETE all data from all tables
5. Mark user as needing setup
6. Redirect to /setup/welcome
```

## Security Architecture

### File Upload Security
- **File Size Limits**: Max 10MB per CSV file
- **File Type Validation**: Only .csv extension allowed
- **Content Validation**: Verify CSV structure before parsing
- **Filename Sanitization**: Remove special characters, prevent path traversal
- **Virus Scanning**: (Optional) Integrate ClamAV for production

### Session Management
- Flask session cookie (httponly, secure, samesite=strict)
- No server-side session store needed (single user)
- CSRF tokens on all forms

### API Security
- CSRF protection on all POST/PUT/DELETE endpoints
- Rate limiting on upload endpoints (prevent abuse)
- Input validation on all user inputs
- SQL injection prevention via SQLAlchemy ORM

### nginx Security
- TLS 1.2+ only
- Strong cipher suites (ECDHE, AES-GCM)
- HSTS with long max-age
- Security headers (X-Frame-Options, CSP, etc.)
- Request size limits
- Timeout configurations

## Performance Considerations

### Database Optimization
- Indexes on: snapshot_date, broker_name, symbol
- Connection pooling via SQLAlchemy
- Lazy loading for relationships
- Periodic VACUUM for SQLite maintenance

### Caching Strategy
- ETF/MF holdings cached for 24 hours (reduce API calls)
- Risk metrics calculated on-demand (not pre-computed)
- Frontend caches theme preference in localStorage

### Async Processing
- Initial data fetch may take 30-60 seconds
- Show loading spinner with progress indicator
- Consider background task queue for future (Celery + Redis)

## Error Handling

### CSV Upload Errors
- Invalid file format: Show user-friendly error with example format
- Parsing failures: Log error, skip invalid rows, notify user
- Missing required columns: Clear error message listing required columns
- File too large: 413 error with size limit message
- Unsupported broker: 400 error with list of supported brokers

### Data Processing Errors
- Missing ETF/MF data: Flag as "Unable to analyze" in UI
- Parse failures: Log error, skip holding, notify user
- Network timeouts (mstarpy): Retry with exponential backoff (3 attempts)

### Database Errors
- Connection failures: Retry logic with circuit breaker
- Constraint violations: Show user-friendly error message
- Disk full: Alert user to free space or reduce retention limit

## Deployment Workflow

1. Build Docker images: `docker-compose build`
2. Generate SSL certificates: `./nginx/ssl/generate_cert.sh`
3. Create `.env` file with encryption key
4. Start services: `docker-compose up -d`
5. Access at: `https://localhost`
6. Follow first-time setup wizard
7. Monitor logs: `docker-compose logs -f app`

## Backup Strategy

### Database Backups
- SQLite file at `/data/portfolio.db`
- Simple file copy for backup
- Recommended: Daily cron job to copy to external drive
- Script: `cp /data/portfolio.db /backups/portfolio_$(date +%Y%m%d).db`

### Credential Recovery
- No encrypted credentials stored (CSV-only approach)
- Users download CSVs directly from broker websites
- No need for encryption key management