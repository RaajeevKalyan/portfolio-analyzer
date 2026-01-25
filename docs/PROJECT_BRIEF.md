# Portfolio Risk Analyzer - Project Brief

## Overview
A local web-based portfolio analysis tool that aggregates positions across multiple brokers, analyzes risk concentrations, identifies ETF/mutual fund overlaps, and tracks portfolio composition over time.

## Core Functionality

### 1. Multi-Broker CSV Import
- **Supported Brokers**: Merrill Lynch, Fidelity, Webull, Robinhood, Schwab
- **Import Method**: Drag-and-drop or browse CSV files exported from broker websites
- **CSV Parsers**: Broker-specific parsers handle different CSV formats
- **First-Run Setup**: User uploads CSV from each broker they have accounts with

### 2. Portfolio Data Management
- **Manual Upload**: User uploads new CSV files to refresh portfolio data
- **Historical Snapshots**: Retained for last N uploads (user-configurable, default 25)
- **Initial Load**: Parses CSV and creates first snapshot per broker
- **Data Persistence**: All snapshots stored with timestamp and source filename

### 3. Holdings Analysis
- **ETF/Mutual Fund Parsing**: Top 50 holdings via mstarpy (fallback to custom script for top 25)
- **Position Aggregation**: Combines holdings across all broker CSV uploads
- **Underlying Stock Resolution**: Breaks down ETFs/MFs to individual stocks
- **CSV Format Handling**: Flexible parsers for each broker's export format

### 4. Risk Analysis & Alerts

#### Single Stock Concentration
- **Threshold**: >20% of total portfolio value
- **Alert**: Red flag with visual indicator
- **Display**: Pie chart of all offenders with valuations and percentages

#### ETF/Mutual Fund Overlap
- **Threshold**: >70% overlap in top holdings
- **Alert**: Separate high-risk section
- **Display**: Matrix or list showing overlapping funds

#### Sector Concentration
- **Analysis**: Aggregate sector exposure across all holdings
- **Alerts**: Flag over-concentration in single sectors
- **Display**: Sector breakdown visualization

#### Geographic Exposure
- **Analysis**: Regional distribution of holdings
- **Alerts**: Flag over-concentration in single markets
- **Display**: Geographic breakdown visualization

### 5. Visualization & Reporting
- **Dashboard**: Total net worth across all portfolios
- **Current Holdings**: Detailed table with stock/fund breakdown
- **Risk Summary**: All flagged concentrations and overlaps
- **Historical Trends**: Charts showing how top offenders' weightage changed over time
- **Time Range**: Selectable based on available snapshots

### 6. Data Management
- **Upload CSV**: Drag-and-drop or browse interface per broker card
- **Clear History**: Button to wipe all historical snapshots
- **Clear All Data**: Nuclear option to reset database (with double confirmation)
- **Re-upload**: Update any broker's data by uploading a new CSV
- **Export**: (Future consideration) CSV/JSON export capability

## Technical Stack

### Backend
- **Framework**: Flask
- **WSGI Server**: Gunicorn (3-5 workers)
- **Database**: SQLite with SQLAlchemy ORM
- **OAuth**: Authlib or broker-specific Python SDKs
- **Encryption**: Fernet (cryptography library) for credentials
- **Scheduling**: Manual only (no APScheduler needed)
- **Data Source**: mstarpy + custom holdings scraper fallback

### Frontend
- **UI Framework**: Bootstrap 5
- **Charts**: Chart.js (clean, modern, excellent docs)
- **Theme**: Light theme default with dark mode toggle (user preference stored)
- **Interactivity**: Vanilla JavaScript + Fetch API
- **Desktop Only**: No mobile responsive requirements

### Infrastructure
- **Containerization**: Docker + Docker Compose
- **Reverse Proxy**: nginx with HTTPS only
- **Security**: OWASP Top 10 hardening, A-rated SSL configuration
- **TLS**: Strong cipher suites only
- **Access**: localhost only (127.0.0.1)

## Security Requirements

### Application Layer
- Single-user mode (no multi-user authentication needed)
- Secure file upload handling (validate CSV format, size limits)
- CSRF protection on all forms
- Input validation and sanitization
- Secure session management

### Network Layer
- **HTTPS Only**: Port 80 disabled/redirected
- **TLS 1.2+**: Modern cipher suites only
- **HSTS**: Strict-Transport-Security headers
- **Security Headers**: X-Frame-Options, X-Content-Type-Options, CSP
- **nginx Hardening**: OWASP recommendations implemented

### Data Layer
- Database file permissions locked down
- No sensitive data in logs
- CSV file validation before processing
- Sanitize uploaded filenames
- Volume mounts for data persistence

## User Flows

### First-Time Setup
1. User accesses https://localhost
2. Welcome screen with dashboard
3. Sees 5 broker cards (Merrill Lynch, Fidelity, Webull, Robinhood, Schwab) in "No data yet" state
4. User downloads CSV from broker website (outside app)
5. Drags CSV onto appropriate broker card OR clicks Browse button
6. App validates and parses CSV
7. Creates initial snapshot for that broker
8. Card updates to show net worth and position count
9. Repeat for other brokers as desired
10. Risk analysis automatically updates with combined data

### Regular Usage
1. User accesses dashboard (shows last snapshot data for each broker)
2. Views current portfolio breakdown and net worth
3. Checks risk alerts and concentrations
4. When ready to refresh a broker's data:
   a. Download new CSV from broker website
   b. Upload to corresponding broker card
   c. App creates new snapshot for that broker only
   d. Risk analysis updates
5. Views historical trends across all brokers
6. Adjusts settings (snapshot retention, theme, etc.)

### Data Management
1. User navigates to settings
2. Can clear historical snapshots (confirmation required)
3. Can reset entire database (double confirmation)
4. Can adjust snapshot retention limit
5. Can remove/re-add broker cards

## Out of Scope (Future Enhancements)
- Multi-user support
- OAuth integration with broker APIs
- Automatic scheduled refreshes
- Public cloud deployment
- Mobile app/responsive design
- Real-time price updates
- Trade execution
- Tax lot analysis
- Performance attribution
- What-if scenario modeling

## Success Criteria
- Successfully parses CSV files from all 5 supported brokers
- Accurately aggregates positions across broker accounts
- Correctly identifies stock concentrations >20%
- Detects ETF/MF overlaps >70%
- Shows sector and geographic concentrations
- Historical trend visualization works for 25+ snapshots
- SSL configuration achieves A rating on SSL Labs
- No security vulnerabilities in OWASP Top 10 categories
- Clean, intuitive UI with light/dark theme toggle
- Sub-second page loads for typical portfolio sizes (<1000 positions)
- Drag-and-drop CSV upload works smoothly
- Clear error messages for invalid CSV formats

## Constraints
- Localhost deployment only
- Desktop browsers only (Chrome, Firefox, Safari latest versions)
- Manual CSV upload only (no automatic data refresh)
- Dependent on user downloading CSVs from broker websites
- ETF/MF holdings limited to top 25-50 (data source dependent)
- CSV format variations may require parser updates