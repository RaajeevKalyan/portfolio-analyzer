# CONTEXT.md - Portfolio Risk Analyzer

## 🎯 Quick Reference
**Paste this file with your requests to give me full context without reviewing all code.**

---

## Project Summary
A local, Docker-based Flask web app that aggregates portfolio data from multiple brokers (Schwab, Robinhood, Merrill Lynch, Fidelity), analyzes risk concentrations, identifies ETF/mutual fund overlaps, and tracks portfolio composition over time.

## Tech Stack
- **Backend**: Flask + Gunicorn + SQLAlchemy + SQLite (file-based, NOT a container)
- **Frontend**: Bootstrap 5 + Chart.js + Vanilla JS
- **Infrastructure**: Docker (2 containers: nginx + Flask app)
- **Data Sources**: Broker APIs (OAuth 2.0) + mstarpy (ETF/MF holdings)
- **Security**: Fernet encryption, OWASP hardening, TLS 1.2+

### Container Architecture (2 Containers)
1. **nginx container** - Reverse proxy, HTTPS termination, security headers
2. **Flask app container** - Application logic, Gunicorn WSGI server
3. **NOT a container** - SQLite database (just a file: `./data/portfolio.db`)

SQLite runs in-process within the Flask app. No separate database container needed.

## Core Features
1. Multi-broker OAuth integration (manual refresh only)
2. Portfolio aggregation and position consolidation
3. ETF/MF underlying holdings analysis (top 50 via mstarpy, fallback to top 25)
4. Risk analysis:
   - Stock concentration (>20% = red flag)
   - ETF/MF overlap (>70% = high risk)
   - Sector concentration
   - Geographic exposure
5. Historical trend tracking (user-configurable snapshot retention, default 25)
6. Data management (clear history, reset all data)
7. Light/dark theme toggle

## Architecture Decisions

### Database Schema
- **UserSettings**: Theme preference, snapshot retention limit
- **BrokerCredential**: Encrypted OAuth tokens per broker
- **PortfolioSnapshot**: Point-in-time portfolio state
- **Holding**: Individual positions (stocks, ETFs, MFs)
- **UnderlyingHolding**: Resolved ETF/MF constituents
- **RiskMetrics**: Calculated risk indicators per snapshot

### Key Workflows
1. **First-time setup**: Wizard → Connect brokers → OAuth flow → Initial data pull → Dashboard
2. **Manual refresh**: Button → Fetch positions → Parse ETFs/MFs → Calculate risk → Update UI
3. **Historical view**: Fetch last N snapshots → Build time-series → Render charts
4. **Data cleanup**: Confirm → Delete old snapshots OR reset entire database

### Security Approach
- **Credentials**: Fernet encryption at rest, key in environment variable
- **Network**: HTTPS only (port 80 redirects), TLS 1.2+, strong ciphers
- **Application**: CSRF protection, input validation, SQL injection prevention via ORM
- **Infrastructure**: nginx with OWASP Top 10 hardening, security headers, rate limiting

## File Organization

```
portfolio-analyzer/
├── docker-compose.yml          # Service orchestration
├── Dockerfile                  # Flask app container
├── requirements.txt            # Python dependencies
├── .env                        # Secrets (gitignored)
├── nginx/
│   ├── Dockerfile              # nginx container
│   ├── nginx.conf              # Proxy config with security
│   └── ssl/                    # Self-signed certificates
├── app/
│   ├── main.py                 # Flask entry point
│   ├── config.py               # Configuration
│   ├── models.py               # SQLAlchemy models
│   ├── database.py             # DB connection
│   ├── encryption.py           # Fernet wrapper
│   ├── routes/                 # Flask routes
│   │   ├── auth.py             # OAuth flows
│   │   ├── dashboard.py        # Main view
│   │   ├── portfolio.py        # Holdings table
│   │   ├── settings.py         # User preferences
│   │   └── api.py              # AJAX endpoints
│   ├── services/               # Business logic
│   │   ├── broker_base.py      # Abstract broker interface
│   │   ├── [broker]_broker.py  # Concrete implementations
│   │   ├── holdings_parser.py  # mstarpy + fallback
│   │   ├── portfolio_aggregator.py
│   │   └── risk_analyzer.py
│   ├── utils/                  # Helpers
│   ├── static/                 # CSS, JS, images
│   └── templates/              # Jinja2 templates
├── data/                       # SQLite database (gitignored)
└── logs/                       # Application logs (gitignored)
```

## UI Layout

### Dashboard
```
┌─────────────────────────────────────────────────────┐
│ Navbar: Logo | Dashboard | Portfolio | History | Settings | [Theme] │
├─────────────────────────────────────────────────────┤
│ [Net Worth Card] [Last Updated] [Risk Level]       │
│ [Donut Chart: Asset Allocation]                    │
│ [Risk Alerts] | [Top Holdings Table]               │
└─────────────────────────────────────────────────────┘
```

### Color Palette
- Light: White bg (#FFFFFF), Primary (#0066CC), Danger (#DC3545)
- Dark: Dark bg (#1A1D21), Primary (#4A9EFF), Danger (#FF6B6B)

### Charts
- Chart.js for all visualizations
- Donut (portfolio allocation), Pie (concentrations), Line (trends), Bar (sectors/geography)

## Critical Constraints

### DO NOT CHANGE:
1. **Single-user mode**: No multi-user auth system
2. **Manual refresh only**: No automatic data pulls
3. **Desktop-only UI**: No mobile responsive requirements
4. **Localhost deployment**: No public cloud features
5. **SQLite database**: No migration to other databases
6. **OAuth flow**: Full callback URL setup (not manual token entry)
7. **HTTPS only**: Port 80 must redirect to 443
8. **Fernet encryption**: Do not switch to other encryption methods

### MUST FOLLOW:
1. **OWASP Top 10**: All mitigations documented in SECURITY_SPEC.md
2. **nginx hardening**: Security headers, TLS 1.2+, strong ciphers
3. **Input validation**: All user inputs validated/sanitized
4. **CSRF protection**: All state-changing operations protected
5. **Encrypted storage**: OAuth tokens encrypted at rest
6. **No browser storage**: localStorage/sessionStorage not used (artifacts limitation)

## Common Modification Patterns

### Adding a New Broker
1. Create `app/services/[broker]_broker.py` extending `broker_base.py`
2. Implement OAuth methods: `get_auth_url()`, `exchange_code()`, `refresh_token()`, `fetch_positions()`
3. Add broker to allowed list in validators
4. Add OAuth callback route: `/oauth/callback/[broker]`
5. Update UI: Add broker card in setup wizard
6. Add credentials to `.env.example`

### Adding a New Risk Metric
1. Add calculation to `app/services/risk_analyzer.py`
2. Add field to `RiskMetrics` model in `app/models.py`
3. Create database migration (Alembic)
4. Update dashboard template to display metric
5. Add chart visualization in `static/js/charts.js`

### Changing UI Theme
1. Modify `static/css/light-theme.css` or `dark-theme.css`
2. Update color variables in `:root`
3. Test both themes for contrast/readability
4. No changes to Bootstrap base needed

### Adjusting Security Settings
1. nginx config: `nginx/nginx.conf` (headers, ciphers, timeouts)
2. Flask config: `app/config.py` (session, CSRF, cookies)
3. Encryption: `app/encryption.py` (only change if rotating keys)
4. Always test with SSL Labs after changes

## Prompt Template for Modifications

```
I need to [describe what you want to change/add].

Context: [Paste relevant sections from CONTEXT.md]

Current behavior: [Describe current state]
Desired behavior: [Describe what you want]

Constraints:
- [Any specific requirements]
- Must maintain [security/architecture principles]

Files likely affected:
- [List files you think need changes]

Please:
1. Confirm approach before generating code
2. Show only changed sections (not entire files)
3. Explain any security/architecture implications
```

## Development Workflow

### Making Code Changes
1. Modify code in `app/` directory
2. Test locally: `docker-compose up --build`
3. Verify functionality in browser
4. Check logs: `docker-compose logs -f app`
5. If OK, commit changes

### Database Schema Changes
1. Modify models in `app/models.py`
2. Create migration: `alembic revision --autogenerate -m "description"`
3. Review migration file
4. Apply migration: `alembic upgrade head`
5. Test data integrity

### Debugging
- **App errors**: `docker-compose logs app`
- **nginx errors**: `docker-compose logs nginx`
- **Database issues**: `sqlite3 data/portfolio.db`
- **OAuth flow**: Enable debug logging in `app/routes/auth.py`

## Known Limitations

### Data Sources
- mstarpy may not return holdings for all ETFs/MFs → fallback to custom scraper
- Broker APIs have rate limits → implement exponential backoff
- Historical data limited by snapshot retention setting

### Browser Compatibility
- Requires modern browser (Chrome, Firefox, Safari latest)
- Self-signed SSL certificate warning expected
- No Internet Explorer support

### Performance
- Large portfolios (>1000 positions) may take 30-60s to refresh
- Chart rendering may be slow with >100 historical snapshots
- SQLite has concurrent write limitations (single user mitigates this)

## Version Information
- Python: 3.11
- Flask: 3.0.0
- SQLAlchemy: 2.0.23
- Bootstrap: 5.3
- Chart.js: 4.x
- nginx: 1.25

## Quick Commands

```bash
# Start services
docker-compose up -d

# Rebuild and restart app only
docker-compose up -d --build app

# View logs
docker-compose logs -f app

# Stop services
docker-compose down

# Backup database
cp data/portfolio.db backups/portfolio_$(date +%Y%m%d).db

# Generate new encryption key
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Test nginx config
docker-compose exec nginx nginx -t

# Access database
sqlite3 data/portfolio.db

# Check SSL configuration
openssl s_client -connect localhost:443 -servername localhost
```

## Getting Help

### For Code Changes
Paste this CONTEXT.md + specific request using template above

### For Architecture Questions
Reference: ARCHITECTURE.md for system design details

### For Security Changes
Reference: SECURITY_SPEC.md for OWASP compliance requirements

### For UI Changes
Reference: UI_SPEC.md for design system and components

### For Docker Issues
Reference: DOCKER_SETUP.md for container configuration

---

## 📌 Remember
- This is a **single-user**, **localhost-only** tool
- Security is critical: OAuth tokens, portfolio data must be protected
- Manual refresh only: No automatic data pulls
- Desktop browsers only: No mobile responsive design needed
- Always test SSL configuration after nginx changes
- Keep .env file backed up securely (contains encryption key)