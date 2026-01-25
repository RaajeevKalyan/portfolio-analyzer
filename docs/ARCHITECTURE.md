# Architecture - Portfolio Risk Analyzer

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
│   ├── encryption.py
│   ├── main.py (Flask app entry)
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── auth.py (OAuth flows)
│   │   ├── dashboard.py
│   │   ├── portfolio.py
│   │   ├── settings.py
│   │   └── api.py (AJAX endpoints)
│   ├── services/
│   │   ├── __init__.py
│   │   ├── broker_base.py
│   │   ├── schwab_broker.py
│   │   ├── robinhood_broker.py
│   │   ├── merrill_broker.py
│   │   ├── fidelity_broker.py
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

### Broker Credentials
```python
class BrokerCredential(Model):
    id: int (PK)
    broker_name: str ('schwab' | 'robinhood' | 'merrill' | 'fidelity')
    encrypted_access_token: bytes
    encrypted_refresh_token: bytes
    token_expires_at: datetime
    is_active: bool
    last_synced_at: datetime
    created_at: datetime
    updated_at: datetime
```

### Portfolio Snapshot
```python
class PortfolioSnapshot(Model):
    id: int (PK)
    snapshot_date: datetime
    total_value: decimal
    total_positions: int
    created_at: datetime
    
    # Relationships
    holdings: List[Holding]
    risk_metrics: RiskMetrics
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
- **auth.py**: OAuth callback handling, token exchange, credential storage
- **dashboard.py**: Main dashboard view, net worth display
- **portfolio.py**: Detailed holdings view, position tables
- **settings.py**: User preferences, broker management, data cleanup
- **api.py**: AJAX endpoints for refresh, chart data, risk calculations

### Services Layer

#### Broker Services
- **broker_base.py**: Abstract base class defining broker interface
- **[broker]_broker.py**: Concrete implementations for each broker
  - OAuth flow initiation
  - Token refresh logic
  - Position fetching
  - Account aggregation

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
- **validators.py**: Input validation, data sanitization
- **helpers.py**: Date formatting, number formatting, common utilities
- **encryption.py**: Fernet-based credential encryption/decryption

## Data Flow

### Initial Setup Flow
```
1. User lands on /setup/welcome
2. Selects broker to connect
3. Redirects to broker OAuth page
4. Broker redirects back to /oauth/callback/{broker}
5. Exchange code for tokens
6. Encrypt and store tokens in DB
7. Trigger initial position fetch
8. Create first PortfolioSnapshot
9. Parse ETF/MF holdings
10. Calculate risk metrics
11. Redirect to dashboard
```

### Manual Refresh Flow
```
1. User clicks "Refresh Portfolio" button
2. AJAX POST to /api/refresh
3. For each active broker:
   a. Refresh OAuth token if needed
   b. Fetch current positions
4. Create new PortfolioSnapshot
5. For each holding:
   a. If ETF/MF, fetch underlying holdings
   b. Store in holdings table
6. Aggregate all underlying positions
7. Calculate risk metrics
8. Return updated data as JSON
9. Frontend updates charts and tables
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

### Encryption Strategy
- **Fernet Symmetric Encryption**: For OAuth tokens at rest
- **Key Management**: 32-byte key stored in environment variable
- **Key Rotation**: Manual process (decrypt all, re-encrypt with new key)

### Session Management
- Flask session cookie (httponly, secure, samesite=strict)
- No server-side session store needed (single user)
- CSRF tokens on all forms

### API Security
- CSRF protection on all POST/PUT/DELETE endpoints
- Rate limiting on OAuth callbacks (prevent brute force)
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

### OAuth Errors
- Token expiration: Auto-refresh if refresh token valid
- Invalid credentials: Prompt user to re-authenticate
- Broker API down: Graceful degradation, show last snapshot

### Data Processing Errors
- Missing ETF/MF data: Flag as "Unable to analyze" in UI
- Parse failures: Log error, skip holding, notify user
- Network timeouts: Retry with exponential backoff (3 attempts)

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
- Encryption key stored in `.env`
- **Critical**: Backup `.env` file securely
- Without key, cannot decrypt stored tokens
- Consider password manager for key storage