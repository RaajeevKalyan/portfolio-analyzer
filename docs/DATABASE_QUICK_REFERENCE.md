# Database Quick Reference

## 🎯 Common Operations

### Initialize Database
```bash
# From container (recommended)
docker-compose exec app python scripts/init_db.py

# From host
python scripts/init_db.py
```

### Access Database
```bash
# SQLite command line
sqlite3 data/portfolio.db

# Inside SQLite:
.tables                           # List tables
.schema broker_accounts          # Show table structure
SELECT * FROM broker_accounts;   # Query data
.quit                            # Exit
```

### Python Shell Access
```bash
# Open Python shell in container
docker-compose exec app python

# Inside Python:
from app.database import get_session
from app.models import BrokerAccount, PortfolioSnapshot

session = get_session()
brokers = session.query(BrokerAccount).all()
print(brokers)
session.close()
```

## 📊 Model Cheat Sheet

### Create Records
```python
from app.database import get_session
from app.models import BrokerAccount
from datetime import datetime

session = get_session()

broker = BrokerAccount(
    broker_name='merrill',
    account_number_last4='1234',
    account_nickname='My Merrill',
    last_uploaded_at=datetime.utcnow()
)
session.add(broker)
session.commit()
session.close()
```

### Read Records
```python
# Get all
brokers = session.query(BrokerAccount).all()

# Filter
merrill = session.query(BrokerAccount).filter_by(broker_name='merrill').first()

# With relationships
from sqlalchemy.orm import joinedload
broker = session.query(BrokerAccount).options(
    joinedload(BrokerAccount.portfolio_snapshots)
).first()
```

### Update Records
```python
broker = session.query(BrokerAccount).filter_by(id=1).first()
broker.account_nickname = 'Updated Name'
session.commit()
```

### Delete Records
```python
broker = session.query(BrokerAccount).filter_by(id=1).first()
session.delete(broker)  # Cascade deletes snapshots and holdings
session.commit()
```

## 🔗 Relationships

### BrokerAccount → PortfolioSnapshots
```python
broker = session.query(BrokerAccount).first()
snapshots = broker.portfolio_snapshots  # List of snapshots
print(f"Broker has {len(snapshots)} snapshots")
```

### PortfolioSnapshot → Holdings
```python
snapshot = session.query(PortfolioSnapshot).first()
holdings = snapshot.holdings  # List of holdings
for holding in holdings:
    print(f"{holding.symbol}: ${holding.total_value}")
```

### AggregateSnapshot → RiskMetrics
```python
aggregate = session.query(AggregateSnapshot).first()
risk = aggregate.risk_metrics  # One-to-one
if risk:
    print(f"Risk level: {risk.risk_level}")
    print(f"Flags: {risk.total_risk_flags}")
```

## 📦 JSON Field Access

### Set JSON Data
```python
from app.models import Holding

holding = Holding(...)
holding.underlying_holdings_list = [
    {'symbol': 'AAPL', 'weight': 0.05, 'value': 1000},
    {'symbol': 'MSFT', 'weight': 0.04, 'value': 800}
]
session.add(holding)
session.commit()
```

### Get JSON Data
```python
holding = session.query(Holding).first()
underlying = holding.underlying_holdings_list  # Returns Python list
for item in underlying:
    print(f"{item['symbol']}: {item['weight']:.2%}")
```

### RiskMetrics JSON
```python
risk = session.query(RiskMetrics).first()

# Access as dictionaries/lists
concentrated = risk.concentrated_stocks_list
sectors = risk.sector_breakdown_dict
geography = risk.geography_breakdown_dict

# Set
risk.concentrated_stocks_list = [
    {'symbol': 'AAPL', 'percentage': 0.25, 'value': 50000}
]
risk.sector_breakdown_dict = {
    'Technology': 0.40,
    'Healthcare': 0.20
}
```

## 🔍 Useful Queries

### Latest Snapshot per Broker
```python
from sqlalchemy import func

latest = session.query(
    PortfolioSnapshot.broker_account_id,
    func.max(PortfolioSnapshot.snapshot_date).label('latest_date')
).group_by(PortfolioSnapshot.broker_account_id).all()
```

### Total Portfolio Value
```python
from sqlalchemy import func

total = session.query(
    func.sum(PortfolioSnapshot.total_value)
).filter(
    PortfolioSnapshot.snapshot_date == 'latest_date'  # Adjust for your logic
).scalar()
```

### Count Holdings by Type
```python
from sqlalchemy import func

counts = session.query(
    Holding.asset_type,
    func.count(Holding.id)
).group_by(Holding.asset_type).all()

for asset_type, count in counts:
    print(f"{asset_type}: {count}")
```

### Find Concentrated Stocks
```python
portfolio_total = 100000  # Get from snapshot
threshold = 0.20

concentrated = session.query(UnderlyingHolding).filter(
    UnderlyingHolding.percentage_of_portfolio > threshold
).all()

for stock in concentrated:
    print(f"{stock.symbol}: {stock.percentage_of_portfolio:.2%}")
```

## 🛠️ Maintenance Commands

### Vacuum Database (Reclaim Space)
```bash
sqlite3 data/portfolio.db "VACUUM;"
```

### Analyze Database (Update Statistics)
```bash
sqlite3 data/portfolio.db "ANALYZE;"
```

### Check Database Size
```bash
ls -lh data/portfolio.db
```

### Backup Database
```bash
cp data/portfolio.db backups/portfolio_$(date +%Y%m%d).db
```

### Check Integrity
```bash
sqlite3 data/portfolio.db "PRAGMA integrity_check;"
```

## 🔐 Context Manager Usage

### Automatic Commit/Rollback
```python
from app.database import db_session

# Use context manager
with db_session() as session:
    broker = BrokerAccount(broker_name='fidelity')
    session.add(broker)
    # Auto-commits on success, auto-rollbacks on error
```

## ⚠️ Common Pitfalls

### Don't Forget to Close Sessions
```python
# BAD
session = get_session()
data = session.query(Model).all()
# Session left open!

# GOOD
session = get_session()
try:
    data = session.query(Model).all()
finally:
    session.close()

# BETTER
with db_session() as session:
    data = session.query(Model).all()
```

### Commit After Changes
```python
# BAD
broker.account_nickname = 'New Name'
# No commit - changes lost!

# GOOD
broker.account_nickname = 'New Name'
session.commit()
```

### Handle Exceptions
```python
try:
    session.add(broker)
    session.commit()
except Exception as e:
    session.rollback()
    print(f"Error: {e}")
finally:
    session.close()
```

## 📚 Model Reference

### Supported Brokers
```python
SUPPORTED_BROKERS = ['merrill', 'fidelity', 'webull', 'robinhood', 'schwab']
```

### Asset Types
```python
ASSET_TYPES = ['stock', 'etf', 'mutual_fund', 'bond', 'cash', 'other']
```

### Account Types
```python
ACCOUNT_TYPES = ['taxable', 'ira', '401k', 'roth']
```

### Risk Levels
```python
RISK_LEVELS = ['low', 'medium', 'high']
```

### Theme Preferences
```python
THEMES = ['light', 'dark']
```