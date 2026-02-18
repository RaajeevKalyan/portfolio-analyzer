# Portfolio Analyzer - Continuation Prompt

Use this prompt to continue development in a new chat session.

---

## Context Prompt

```
I'm continuing development on a Portfolio Risk Analyzer Flask application. Here's the context:

## Project Overview
A web-based portfolio analyzer that:
- Parses CSV exports from brokers (Merrill Lynch implemented, others planned)
- Resolves ETF/Mutual Fund underlying holdings using mstarpy 8.0.3
- Fetches stock info (sector, country) using yfinance
- Displays risk analysis (concentration, sector allocation, geography)
- Shows fund expense analysis with peer recommendations
- Projects future portfolio value with risk metrics

## Tech Stack
- **Backend**: Flask, SQLAlchemy, SQLite
- **Frontend**: Vanilla JS, Chart.js, Bootstrap 5
- **APIs**: mstarpy 8.0.3 (Morningstar), yfinance (Yahoo Finance)
- **Deployment**: Docker, nginx reverse proxy

## Key Files Structure
```
app/
├── main.py                    # Flask app factory, route registration
├── models.py                  # SQLAlchemy models (BrokerAccount, PortfolioSnapshot, Holding)
├── database.py                # DB session management
├── config.py                  # Configuration
├── routes/
│   ├── upload.py              # CSV upload, broker snapshot API
│   ├── holdings.py            # Holdings API
│   ├── fund_analysis.py       # Expense ratio & peer comparison API
│   └── portfolio_projection.py # Future value projections API
├── services/
│   ├── merrill_csv_parser.py  # Merrill Lynch CSV parser
│   ├── holdings_aggregator.py # Aggregates holdings across brokers
│   ├── holdings_resolver.py   # Resolves ETF/MF underlying holdings (mstarpy)
│   ├── stock_info_service.py  # Fetches sector/country (yfinance)
│   ├── fund_analysis_service.py # Expense ratios, peer search (yfinance + mstarpy)
│   └── portfolio_projection_service.py # Risk metrics, future projections
├── templates/
│   └── dashboard.html         # Main dashboard template
└── static/
    ├── css/
    │   ├── base.css, layout.css, components.css
    │   ├── broker-cards.css   # Broker card tabs (Overview/History/Upload)
    │   ├── fund-analysis.css  # Expense analysis section
    │   └── portfolio-projection.css # Projections & risk metrics
    └── js/
        ├── utils.js, toast.js, settings.js, charts.js, modal.js
        ├── broker-cards.js    # Broker card functionality
        ├── fund-analysis.js   # Fund expense analysis
        └── portfolio-projection.js # Projections chart
```

## Key Design Decisions
1. **mstarpy 8.0.3 API**: Uses `screener_universe()` with fields like `morningstarCategory`, `ongoingCharge`, `medalistRating`, `fundStarRating`, `totalReturn`
2. **Expense Ratios**: Primary source is yfinance `funds_data.fund_operations`, fallback to mstarpy `ongoingCharge`
3. **Peer Search**: Searches by category name keywords, filters by Gold/Silver medalist rating
4. **Caching**: Server-side JSON cache files + client-side sessionStorage for performance
5. **Modular CSS/JS**: Separate files per feature, loaded in dashboard.html

## Recent Features Added
- CSV timestamp extraction from "Exported on:" header
- Fund expense analysis table with annual fees
- Peer fund recommendations by category
- Performance comparison charts (fund vs peers NAV history)
- Portfolio projections with best/worst case scenarios
- Risk metrics: Beta, Sharpe ratio, volatility, alpha

## Known Issues / TODOs
- Peer search may not find Gold/Silver rated peers for all categories
- Some mutual funds don't have expense ratio data in yfinance
- Need to add more broker CSV parsers (Fidelity, Schwab, etc.)

## Current Task
[Describe what you want to work on next]
```

---

## Files to Reference
When continuing, you may want to view these key files:
- `/mnt/user-data/uploads/[your-csv].csv` - Sample CSV for testing
- Check logs for mstarpy API responses
- Clear caches at `/app/data/*.json` if data seems stale

## Test ETFs for Peer Search
These ETFs have well-known categories with multiple peers:
- **VOO** - Large Blend (S&P 500)
- **VTI** - Large Blend (Total Stock Market)
- **QQQ** - Large Growth (Nasdaq 100)
- **VUG** - Large Growth
- **VTV** - Large Value
- **VXUS** - Foreign Large Blend
- **VWO** - Diversified Emerging Markets
- **BND** - Intermediate Core Bond

## Useful Commands
```bash
# View logs
docker logs portfolio-app -f

# Clear all caches
rm /app/data/*.json

# Restart app
docker-compose restart

# Check database
sqlite3 /app/data/portfolio.db "SELECT * FROM holding LIMIT 5;"
```