# Portfolio Risk Analyzer

A self-hosted, Docker-based portfolio analysis tool that aggregates holdings across multiple brokers, identifies risk concentrations, detects ETF/mutual fund overlaps, and tracks portfolio composition over time.

## Features

### 🔗 Multi-Broker Integration
- Connect to Schwab, Robinhood, Merrill Lynch, and Fidelity
- Secure OAuth 2.0 authentication with encrypted credential storage
- Manual portfolio refresh on-demand

### 📊 Risk Analysis
- **Stock Concentration**: Flags individual stocks exceeding 20% of portfolio
- **ETF/MF Overlap**: Detects funds with >70% overlapping holdings
- **Sector Exposure**: Analyzes concentration across market sectors
- **Geographic Distribution**: Tracks regional investment allocation

### 📈 Portfolio Insights
- Real-time net worth aggregation across all brokers
- Detailed holdings breakdown with underlying ETF/MF constituents
- Historical trend tracking for concentrations and allocations
- Clean, professional dashboard with interactive charts

### 🔒 Security-First Design
- HTTPS-only access with TLS 1.2+ and strong ciphers
- OWASP Top 10 hardening implemented
- Fernet encryption for OAuth tokens at rest
- Comprehensive security headers and CSRF protection
- A-rated SSL configuration

### 🎨 User Experience
- Light/dark theme with user preference storage
- Desktop-optimized responsive design
- Chart.js visualizations (pie, donut, line, bar charts)
- Configurable snapshot retention (default 25)

## Prerequisites

- Docker and Docker Compose
- Modern web browser (Chrome, Firefox, Safari)
- Broker accounts with API access (Schwab, Robinhood, Merrill, Fidelity)
- Broker OAuth client credentials

## Quick Start

### 1. Clone and Setup

```bash
# Clone the repository
git clone <repository-url>
cd portfolio-analyzer

# Run setup script
chmod +x setup.sh
./setup.sh
```

This will:
- Create required directories (`data/`, `logs/`, `nginx/ssl/`)
- Copy `.env.example` to `.env`
- Generate self-signed SSL certificates
- Build Docker images

### 2. Configure Environment

Edit `.env` file and add your broker credentials:

```bash
# Generate encryption key
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Edit .env
nano .env
```

Required variables:
```
ENCRYPTION_KEY=your-fernet-key-here
SECRET_KEY=your-flask-secret-here
SCHWAB_CLIENT_ID=...
SCHWAB_CLIENT_SECRET=...
# ... (add credentials for other brokers)
```

### 3. Start Services

```bash
# Start all services in detached mode
docker-compose up -d

# View logs
docker-compose logs -f
```

### 4. Access Application

1. Navigate to: `https://localhost`
2. Accept the self-signed certificate warning (expected behavior)
3. Complete the first-time setup wizard
4. Connect your broker accounts via OAuth
5. Initial portfolio data will be fetched automatically

## Usage

### First-Time Setup
1. **Connect Brokers**: Follow the OAuth flow for each broker
2. **Initial Data Pull**: Application fetches all positions automatically
3. **View Dashboard**: See aggregated portfolio and risk analysis

### Regular Usage
1. **View Dashboard**: Current portfolio snapshot and alerts
2. **Refresh Data**: Click "Refresh Portfolio" to pull latest positions
3. **Analyze Risk**: Review concentration alerts and overlaps
4. **Track Trends**: View historical changes in allocations
5. **Manage Settings**: Adjust retention limits, disconnect brokers

### Data Management
- **Clear Historical Snapshots**: Keeps only the most recent data
- **Reset All Data**: Nuclear option - deletes everything (requires double confirmation)

## Architecture

```
┌─────────────────────────────────────────────────┐
│                Docker Compose                    │
│                                                  │
│  ┌──────────┐         ┌─────────────────────┐  │
│  │  nginx   │────────▶│    Flask App        │  │
│  │  :443    │  proxy  │    (Gunicorn)       │  │
│  │          │         │                     │  │
│  └──────────┘         └─────────┬───────────┘  │
│                                 │               │
│                                 ▼               │
│                       ┌──────────────────┐      │
│                       │  SQLite Database │      │
│                       │  (Encrypted)     │      │
│                       └──────────────────┘      │
└─────────────────────────────────────────────────┘
```

### Tech Stack
- **Backend**: Python 3.11, Flask, SQLAlchemy, Gunicorn
- **Frontend**: Bootstrap 5, Chart.js, Vanilla JavaScript
- **Database**: SQLite with encrypted credential storage
- **Infrastructure**: Docker, nginx (reverse proxy), Let's Encrypt ready
- **Security**: Fernet encryption, OWASP hardening, TLS 1.2+

## Project Structure

```
portfolio-analyzer/
├── app/                    # Flask application
│   ├── routes/            # HTTP endpoints
│   ├── services/          # Business logic (brokers, risk analysis)
│   ├── models.py          # Database models
│   ├── templates/         # Jinja2 templates
│   └── static/            # CSS, JS, images
├── nginx/                 # Reverse proxy configuration
│   ├── nginx.conf        # Security-hardened config
│   └── ssl/              # SSL certificates
├── docker-compose.yml     # Service orchestration
├── Dockerfile            # Application container
├── requirements.txt      # Python dependencies
└── data/                 # Persistent storage (gitignored)
```

## Configuration

### Environment Variables
See `.env.example` for all available options.

Key variables:
- `ENCRYPTION_KEY`: Fernet key for token encryption (required)
- `SECRET_KEY`: Flask session key (required)
- `DATABASE_URL`: SQLite database path (default: `sqlite:///data/portfolio.db`)
- `[BROKER]_CLIENT_ID/SECRET`: OAuth credentials per broker

### User Settings
Configurable via Settings page:
- Theme preference (light/dark/auto)
- Snapshot retention limit (1-100, default 25)
- Broker connections (add/remove)

## Security

### Implemented Protections
✅ HTTPS-only (port 80 redirects to 443)
✅ TLS 1.2/1.3 with strong cipher suites
✅ HSTS, CSP, and all recommended security headers
✅ CSRF protection on all forms
✅ SQL injection prevention (SQLAlchemy ORM)
✅ XSS protection (template auto-escaping)
✅ Fernet encryption for OAuth tokens
✅ Rate limiting on authentication endpoints
✅ Input validation and sanitization
✅ Secure session management

### Best Practices
- Never commit `.env` file or SSL certificates
- Regularly update dependencies: `pip-audit`
- Rotate encryption key annually
- Backup database securely
- Review logs for suspicious activity

## Maintenance

### Backups
```bash
# Backup database
./backup.sh

# Manual backup
cp data/portfolio.db backups/portfolio_$(date +%Y%m%d).db
cp .env backups/  # Store securely!
```

### Updates
```bash
# Update application code
git pull

# Rebuild and restart
docker-compose build
docker-compose up -d

# View logs
docker-compose logs -f app
```

### Database Migrations
```bash
# After modifying models.py
docker-compose exec app alembic revision --autogenerate -m "description"
docker-compose exec app alembic upgrade head
```

### Monitoring
```bash
# Application logs
docker-compose logs -f app

# nginx logs
docker-compose logs -f nginx

# Database access
sqlite3 data/portfolio.db

# Health check
curl -k https://localhost/health
```

## Troubleshooting

### Common Issues

**Self-signed certificate warning**
- Expected behavior for local deployment
- Click "Advanced" → "Proceed to localhost (unsafe)"
- Or import certificate into system trust store

**Port 443 already in use**
```bash
# Find conflicting process
sudo lsof -i :443

# Change port in docker-compose.yml if needed
ports:
  - "8443:443"
```

**OAuth flow fails**
- Verify broker credentials in `.env`
- Check redirect URI matches broker configuration
- Review logs: `docker-compose logs -f app`

**Database locked errors**
```bash
# Restart services
docker-compose restart app
```

**Permission denied on data directory**
```bash
# Fix permissions
sudo chown -R 1000:1000 data/
sudo chmod 700 data/
```

## Development

### Running Tests
```bash
# Install dev dependencies
pip install -r requirements-dev.txt

# Run tests
pytest

# With coverage
pytest --cov=app tests/
```

### Code Quality
```bash
# Format code
black app/

# Lint
flake8 app/
pylint app/

# Security audit
pip-audit
bandit -r app/
```

### Contributing
1. Fork the repository
2. Create a feature branch
3. Make changes and add tests
4. Ensure all tests pass
5. Submit a pull request

## Documentation

Detailed documentation available in `/docs`:
- **PROJECT_BRIEF.md**: High-level requirements and scope
- **ARCHITECTURE.md**: System design and data models
- **UI_SPEC.md**: Design system and components
- **SECURITY_SPEC.md**: Security implementation details
- **DOCKER_SETUP.md**: Container configuration
- **CONTEXT.md**: Quick reference for modifications

## Limitations

### Current Constraints
- **Localhost only**: Not designed for public cloud deployment
- **Single user**: No multi-user authentication
- **Manual refresh**: No automatic data pulls
- **Desktop browsers**: Not mobile-responsive
- **SQLite**: Not suitable for high-concurrency (single user is fine)

### Known Issues
- mstarpy may not return holdings for all ETFs/MFs (fallback implemented)
- Large portfolios (>1000 positions) may take 30-60s to refresh
- Broker APIs have rate limits (exponential backoff implemented)

## Roadmap

### Planned Features
- [ ] Multi-user support with authentication
- [ ] Scheduled automatic refreshes
- [ ] Real-time price updates
- [ ] Tax lot analysis
- [ ] Performance attribution
- [ ] What-if scenario modeling
- [ ] Export to CSV/PDF
- [ ] Mobile app

### Future Considerations
- PostgreSQL migration for multi-user support
- Redis caching for performance
- Celery for background tasks
- API for third-party integrations

## License

[Specify your license here]

## Acknowledgments

- [mstarpy](https://github.com/jkoestner/mstarpy) for ETF/MF holdings data
- [Chart.js](https://www.chartjs.org/) for visualizations
- [Bootstrap](https://getbootstrap.com/) for UI framework
- Broker API documentation and support

## Support

For issues, questions, or contributions:
- Open an issue on GitHub
- Review documentation in `/docs`
- Check troubleshooting section above

## Disclaimer

This tool is for personal portfolio analysis only. It does not provide investment advice. Always consult with a qualified financial advisor for investment decisions. Use at your own risk.

---

**Made with ❤️ for personal finance geeks**