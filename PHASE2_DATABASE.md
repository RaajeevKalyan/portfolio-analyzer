# Phase 2: Database Layer

## ✅ What We're Building

This phase creates the database foundation:
- **SQLAlchemy models** for all entities (brokers, snapshots, holdings, risk)
- **Database initialization** script
- **Session management** with proper connection pooling
- **Test data** creation capability

## 📦 Files Created

### Database Layer
```
app/
├── database.py           # SQLAlchemy engine, session management
└── models.py            # All database models

scripts/
├── __init__.py          # Package initializer
└── init_db.py          # Database initialization script
```

## 🗄️ Database Schema

### Entity Relationship Diagram

```
UserSettings (1)
    └─ Global app preferences

BrokerAccount (N)
    ├─ broker_name: 'merrill', 'fidelity', 'webull', 'robinhood', 'schwab'
    ├─ account_number_last4
    └─ last_uploaded_at
    
    └─ PortfolioSnapshot (N) - One per CSV upload
        ├─ snapshot_date
        ├─ total_value
        └─ csv_filename
        
        └─ Holding (N) - Individual positions
            ├─ symbol, quantity, price
            ├─ asset_type: 'stock', 'etf', 'mutual_fund'
            └─ underlying_holdings (JSON) - For ETFs/MFs

AggregateSnapshot (N) - Combines all brokers at a point in time
    ├─ snapshot_date
    ├─ total_value (sum across all brokers)
    └─ portfolio_snapshots (M:N) - Links to individual broker snapshots
    
    ├─ UnderlyingHolding (N) - Resolved ETF/MF constituents
    │   ├─ symbol, total_value
    │   ├─ percentage_of_portfolio
    │   └─ sector, geography
    
    └─ RiskMetrics (1)
        ├─ concentrated_stocks (JSON)
        ├─ overlapping_funds (JSON)
        ├─ sector_breakdown (JSON)
        └─ geography_breakdown (JSON)
```

### Models Overview

#### **UserSettings**
- Snapshot retention limit (default: 25)
- Theme preference ('light' or 'dark')

#### **BrokerAccount**
- Represents a broker connection (Merrill, Fidelity, etc.)
- Tracks when last CSV was uploaded
- Can be marked inactive without deleting data

#### **PortfolioSnapshot**
- Point-in-time snapshot of ONE broker account
- Created each time user uploads a CSV
- Contains total value and position count
- **1:N relationship** with Holdings

#### **AggregateSnapshot**
- Combines ALL brokers at a specific point in time
- Created when user triggers "Calculate Risk" or auto-created on upload
- **M:N relationship** with PortfolioSnapshots (many brokers → one aggregate)
- **1:1 relationship** with RiskMetrics

#### **Holding**
- Individual position (stock, ETF, mutual fund, etc.)
- Stores symbol, quantity, price, total value
- For ETFs/MFs: `underlying_holdings` stores JSON of constituents
- `underlying_parsed` flag indicates if we've fetched ETF/MF data

#### **UnderlyingHolding**
- Aggregated underlying positions across ALL ETFs/MFs in portfolio
- Example: If you hold both VTI and ITOT, AAPL appears once with combined value
- Used for calculating stock concentration risk
- Tracks which holdings contributed to this position (sources)

#### **RiskMetrics**
- Calculated risk analysis for an AggregateSnapshot
- Stores all risk data as JSON for flexibility:
  - `concentrated_stocks`: Stocks >20% of portfolio
  - `overlapping_funds`: ETFs/MFs with >70% overlap
  - `sector_breakdown`: % allocation by sector
  - `geography_breakdown`: % allocation by region
- Overall `risk_level`: 'low', 'medium', 'high'

## 🔧 Key Database Features

### 1. **SQLite WAL Mode**
```python
cursor.execute("PRAGMA journal_mode=WAL")
```
- Write-Ahead Logging enables better concurrency
- Multiple readers can access database while writer is active
- Better for web applications

### 2. **Foreign Key Enforcement**
```python
cursor.execute("PRAGMA foreign_keys=ON")
```
- Ensures referential integrity
- Prevents orphaned records
- Cascade deletes work properly

### 3. **Connection Pooling**
```python
poolclass=StaticPool  # For SQLite single-user
```
- StaticPool keeps one persistent connection
- Prevents "database is locked" errors
- Perfect for single-user localhost deployment

### 4. **JSON Storage**
```python
underlying_holdings = Column(Text, nullable=True)  # Stored as JSON string
```
- Flexible schema for complex nested data
- Easy to query and update
- No need for additional tables for variable-length lists

### 5. **Property Helpers**
```python
@property
def underlying_holdings_list(self):
    return json.loads(self.underlying_holdings)

@underlying_holdings_list.setter
def underlying_holdings_list(self, value):
    self.underlying_holdings = json.dumps(value)
```
- Clean Python interface to JSON data
- Automatic serialization/deserialization
- Type-safe access

## 🚀 Installation & Testing

### Step 1: Update Requirements (Already in requirements.txt)

The database dependencies are already included:
```
SQLAlchemy==2.0.23
alembic==1.13.0
```

### Step 2: Create Database Directories

```bash
# Create data directory if not exists
mkdir -p data
chmod 700 data  # Restrict permissions
```

### Step 3: Initialize Database

**Option A: From Host Machine**
```bash
# Set environment variable (or use .env file)
export DATABASE_URL=sqlite:///data/portfolio.db

# Run initialization script
python scripts/init_db.py
```

**Option B: From Docker Container (Recommended)**
```bash
# Start containers
docker-compose up -d

# Run init script inside container
docker-compose exec app python scripts/init_db.py

# Follow prompts:
# - Create sample data? (yes/no)
```

### Step 4: Verify Database Created

```bash
# Check database file exists
ls -lh data/portfolio.db

# SQLite command-line tool
sqlite3 data/portfolio.db

# Inside SQLite:
.tables  # List all tables
.schema broker_accounts  # See table structure
SELECT * FROM user_settings;  # Query data
.quit
```

## 🧪 Testing Database

### Test 1: Verify Tables Created

```bash
docker-compose exec app python -c "
from app.database import get_engine
from sqlalchemy import inspect

engine = get_engine()
inspector = inspect(engine)
tables = inspector.get_table_names()
print('Tables created:', tables)
print('Total:', len(tables))
"
```

**Expected output:**
```
Tables created: ['aggregate_portfolio_association', 'aggregate_snapshots', 'broker_accounts', 'holdings', 'portfolio_snapshots', 'risk_metrics', 'underlying_holdings', 'user_settings']
Total: 8
```

### Test 2: Verify Sample Data (if created)

```bash
docker-compose exec app python -c "
from app.database import get_session
from app.models import BrokerAccount, PortfolioSnapshot, Holding

session = get_session()

# Query data
accounts = session.query(BrokerAccount).all()
print(f'Broker Accounts: {len(accounts)}')
for account in accounts:
    print(f'  - {account.broker_name} (***{account.account_number_last4})')

snapshots = session.query(PortfolioSnapshot).all()
print(f'Portfolio Snapshots: {len(snapshots)}')
for snapshot in snapshots:
    print(f'  - {snapshot.snapshot_date}: \${snapshot.total_value}')

holdings = session.query(Holding).all()
print(f'Holdings: {len(holdings)}')
for holding in holdings:
    print(f'  - {holding.symbol}: {holding.quantity} @ \${holding.price}')

session.close()
"
```

### Test 3: Test CRUD Operations

```bash
docker-compose exec app python -c "
from app.database import get_session
from app.models import BrokerAccount
from datetime import datetime

session = get_session()

# Create
broker = BrokerAccount(
    broker_name='fidelity',
    account_number_last4='5678',
    account_nickname='Test Account'
)
session.add(broker)
session.commit()
print('Created:', broker)

# Read
broker = session.query(BrokerAccount).filter_by(broker_name='fidelity').first()
print('Read:', broker)

# Update
broker.account_nickname = 'Updated Nickname'
session.commit()
print('Updated:', broker)

# Delete
session.delete(broker)
session.commit()
print('Deleted!')

session.close()
"
```

### Test 4: Test Relationships

```bash
docker-compose exec app python -c "
from app.database import get_session
from app.models import BrokerAccount, PortfolioSnapshot

session = get_session()

# Get broker and its snapshots
broker = session.query(BrokerAccount).first()
if broker:
    print(f'Broker: {broker.broker_name}')
    print(f'Snapshots: {len(broker.portfolio_snapshots)}')
    for snapshot in broker.portfolio_snapshots:
        print(f'  - {snapshot.snapshot_date}: {len(snapshot.holdings)} holdings')

session.close()
"
```

### Test 5: Test JSON Fields

```bash
docker-compose exec app python -c "
from app.database import get_session
from app.models import Holding

session = get_session()

# Create holding with underlying data
holding = Holding(
    portfolio_snapshot_id=1,
    symbol='VTI',
    name='Vanguard Total Stock Market ETF',
    quantity=100,
    price=250.00,
    total_value=25000.00,
    asset_type='etf'
)

# Set underlying holdings using property
holding.underlying_holdings_list = [
    {'symbol': 'AAPL', 'weight': 0.05, 'value': 1250.00},
    {'symbol': 'MSFT', 'weight': 0.04, 'value': 1000.00},
]

session.add(holding)
session.commit()

# Read back
holding = session.query(Holding).filter_by(symbol='VTI').first()
print('Underlying holdings:', holding.underlying_holdings_list)

session.close()
"
```

## 📊 Database Schema Details

### Table: `user_settings`
```sql
CREATE TABLE user_settings (
    id INTEGER PRIMARY KEY,
    snapshot_retention_limit INTEGER DEFAULT 25 NOT NULL,
    theme_preference VARCHAR(10) DEFAULT 'light' NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
);
```

### Table: `broker_accounts`
```sql
CREATE TABLE broker_accounts (
    id INTEGER PRIMARY KEY,
    broker_name VARCHAR(50) NOT NULL,
    account_number_last4 VARCHAR(4),
    account_nickname VARCHAR(100),
    last_uploaded_at DATETIME,
    last_csv_filename VARCHAR(255),
    is_active BOOLEAN DEFAULT 1 NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    UNIQUE (broker_name, account_number_last4)
);
CREATE INDEX idx_broker_name ON broker_accounts(broker_name);
```

### Table: `portfolio_snapshots`
```sql
CREATE TABLE portfolio_snapshots (
    id INTEGER PRIMARY KEY,
    broker_account_id INTEGER NOT NULL REFERENCES broker_accounts(id) ON DELETE CASCADE,
    snapshot_date DATETIME NOT NULL,
    total_value NUMERIC(15, 2) NOT NULL,
    total_positions INTEGER DEFAULT 0 NOT NULL,
    upload_source VARCHAR(50) DEFAULT 'csv_upload' NOT NULL,
    csv_filename VARCHAR(255),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
);
CREATE INDEX idx_broker_snapshot_date ON portfolio_snapshots(broker_account_id, snapshot_date);
CREATE INDEX idx_snapshot_date ON portfolio_snapshots(snapshot_date);
```

### Table: `holdings`
```sql
CREATE TABLE holdings (
    id INTEGER PRIMARY KEY,
    portfolio_snapshot_id INTEGER NOT NULL REFERENCES portfolio_snapshots(id) ON DELETE CASCADE,
    symbol VARCHAR(20) NOT NULL,
    name VARCHAR(255),
    quantity NUMERIC(15, 4) NOT NULL,
    price NUMERIC(15, 4) NOT NULL,
    total_value NUMERIC(15, 2) NOT NULL,
    asset_type VARCHAR(50) NOT NULL,
    account_type VARCHAR(50),
    underlying_holdings TEXT,  -- JSON
    underlying_parsed BOOLEAN DEFAULT 0 NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
);
CREATE INDEX idx_holding_snapshot ON holdings(portfolio_snapshot_id);
CREATE INDEX idx_holding_symbol ON holdings(symbol);
CREATE INDEX idx_holding_asset_type ON holdings(asset_type);
```

## 🔧 Common Database Operations

### Query All Brokers
```python
from app.database import get_session
from app.models import BrokerAccount

session = get_session()
brokers = session.query(BrokerAccount).filter_by(is_active=True).all()
for broker in brokers:
    print(f"{broker.broker_name}: {broker.account_nickname}")
session.close()
```

### Get Latest Snapshot per Broker
```python
from app.database import get_session
from app.models import BrokerAccount, PortfolioSnapshot
from sqlalchemy.orm import joinedload

session = get_session()
brokers = session.query(BrokerAccount).options(
    joinedload(BrokerAccount.portfolio_snapshots)
).all()

for broker in brokers:
    latest = max(broker.portfolio_snapshots, key=lambda s: s.snapshot_date, default=None)
    if latest:
        print(f"{broker.broker_name}: ${latest.total_value} on {latest.snapshot_date}")
    else:
        print(f"{broker.broker_name}: No snapshots")

session.close()
```

### Calculate Total Portfolio Value
```python
from app.database import get_session
from app.models import PortfolioSnapshot, BrokerAccount
from sqlalchemy import func, desc

session = get_session()

# Get latest snapshot per broker
subquery = session.query(
    PortfolioSnapshot.broker_account_id,
    func.max(PortfolioSnapshot.snapshot_date).label('max_date')
).group_by(PortfolioSnapshot.broker_account_id).subquery()

latest_snapshots = session.query(PortfolioSnapshot).join(
    subquery,
    (PortfolioSnapshot.broker_account_id == subquery.c.broker_account_id) &
    (PortfolioSnapshot.snapshot_date == subquery.c.max_date)
).all()

total_value = sum(s.total_value for s in latest_snapshots)
print(f"Total Portfolio Value: ${total_value:,.2f}")

session.close()
```

## ✅ Success Criteria

Phase 2 is complete if:

- [ ] `data/portfolio.db` file exists
- [ ] 8 tables created in database
- [ ] `user_settings` table has 1 row (default settings)
- [ ] Can create BrokerAccount via Python
- [ ] Can create PortfolioSnapshot with Holdings
- [ ] Foreign key constraints work (cascade delete)
- [ ] JSON fields serialize/deserialize correctly
- [ ] No errors in `docker-compose logs app`

## 🐛 Troubleshooting

### Database file not created
```bash
# Check directory exists
ls -la data/

# Check permissions
chmod 700 data/

# Check environment variable
docker-compose exec app env | grep DATABASE_URL
```

### "Table already exists" error
```bash
# Drop and recreate
docker-compose exec app python -c "
from app.database import get_engine, Base
engine = get_engine()
Base.metadata.drop_all(engine)
Base.metadata.create_all(engine)
print('Database recreated!')
"
```

### "Database is locked" error
```bash
# Check if WAL mode is enabled
sqlite3 data/portfolio.db "PRAGMA journal_mode;"
# Should return: wal

# Check for stale connections
docker-compose restart app
```

### Permission denied on data/portfolio.db
```bash
# Fix permissions
sudo chown -R 1000:1000 data/
chmod 600 data/portfolio.db
```

## 📈 Next Steps

**Phase 3: CSV Upload (Merrill Lynch Parser)**
- Create upload route with drag-and-drop UI
- Build Merrill Lynch CSV parser
- Store parsed data in database
- Display broker cards on dashboard

---

## 📝 Notes

- SQLite is perfect for single-user localhost deployment
- WAL mode prevents most locking issues
- JSON fields provide flexibility for variable data
- Cascade deletes keep database clean
- Sample data is optional (for testing only)
- Database file should be backed up regularly