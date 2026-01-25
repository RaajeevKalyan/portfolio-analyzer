# Portfolio Risk Analyzer - Project Brief

## Overview
A local web-based portfolio analysis tool that aggregates positions across multiple brokers, analyzes risk concentrations, identifies ETF/mutual fund overlaps, and tracks portfolio composition over time.

## Core Functionality

### 1. Multi-Broker Integration
- **Supported Brokers**: Schwab, Robinhood, Merrill Lynch, Fidelity
- **Authentication**: OAuth 2.0 with full callback URL setup
- **Credential Storage**: Encrypted in SQLite database
- **First-Run Setup**: Guided broker connection wizard

### 2. Portfolio Data Management
- **Manual Refresh**: User-triggered data pulls via button
- **Historical Snapshots**: Retained for last N pulls (user-configurable, default 25)
- **Initial Load**: Downloads all positions on first connection
- **Data Persistence**: All snapshots stored with timestamp

### 3. Holdings Analysis
- **ETF/Mutual Fund Parsing**: Top 50 holdings via mstarpy (fallback to custom script for top 25)
- **Position Aggregation**: Combines holdings across all brokers
- **Underlying Stock Resolution**: Breaks down ETFs/MFs to individual stocks

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
- **Clear History**: Button to wipe all historical snapshots
- **Clear All Data**: Nuclear option to reset database (with double confirmation)
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
- Encrypted credential storage (Fernet with env-based key)
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
- Encryption key stored in environment (not in code)
- Volume mounts for data persistence

## User Flows

### First-Time Setup
1. User accesses https://localhost
2. Welcome screen with setup wizard
3. Configure broker connections (one by one)
4. OAuth flow for each broker (callback handling)
5. Initial data pull and snapshot creation
6. Redirect to dashboard

### Regular Usage
1. User accesses dashboard (shows last snapshot)
2. Views current portfolio breakdown and net worth
3. Checks risk alerts and concentrations
4. Optionally triggers manual refresh (new snapshot)
5. Views historical trends of risk metrics
6. Adjusts settings (snapshot retention, theme, etc.)

### Data Management
1. User navigates to settings
2. Can clear historical snapshots (confirmation required)
3. Can reset entire database (double confirmation)
4. Can adjust snapshot retention limit

## Out of Scope (Future Enhancements)
- Multi-user support
- Automatic scheduled refreshes
- Public cloud deployment
- Mobile app/responsive design
- Real-time price updates
- Trade execution
- Tax lot analysis
- Performance attribution
- What-if scenario modeling

## Success Criteria
- Successfully connects to all 4 brokers via OAuth
- Accurately aggregates positions across brokers
- Correctly identifies stock concentrations >20%
- Detects ETF/MF overlaps >70%
- Shows sector and geographic concentrations
- Historical trend visualization works for 25+ snapshots
- SSL configuration achieves A rating on SSL Labs
- No security vulnerabilities in OWASP Top 10 categories
- Clean, intuitive UI with light/dark theme toggle
- Sub-second page loads for typical portfolio sizes (<1000 positions)

## Constraints
- Localhost deployment only
- Desktop browsers only (Chrome, Firefox, Safari latest versions)
- Manual data refresh only (no real-time streaming)
- Dependent on broker API availability and rate limits
- ETF/MF holdings limited to top 25-50 (data source dependent)