# Phase 2: Database Layer - Summary

## ✅ Files Created (4 new files)

### Python Code
1. **app/database.py** (150 lines)
   - SQLAlchemy engine setup
   - Session factory and management
   - SQLite WAL mode configuration
   - Context manager for clean session handling

2. **app/models.py** (350+ lines)
   - 7 SQLAlchemy models:
     - `UserSettings` - App preferences
     - `BrokerAccount` - Broker connections
     - `PortfolioSnapshot` - Per-broker snapshots
     - `AggregateSnapshot` - Combined snapshots
     - `Holding` - Individual positions
     - `UnderlyingHolding` - Resolved ETF/MF constituents
     - `RiskMetrics` - Risk analysis results
   - JSON field helpers (properties)
   - Indexes and constraints

3. **scripts/init_db.py** (180 lines)
   - Database initialization script
   - Table creation
   - Sample data generation (optional)
   - Interactive prompts

4. **scripts/__init__.py** (3 lines)
   - Package initializer

### Documentation
5. **PHASE2_DATABASE.md** (450+ lines)
   - Complete database schema documentation
   - ERD (text-based)
   - Installation and testing guide
   - SQL table definitions
   - Troubleshooting guide

6. **DATABASE_QUICK_REFERENCE.md** (250+ lines)
   - Quick command reference
   - CRUD operation examples
   - Common queries
   - Maintenance commands

---

## 🗄️ Database Schema at a Glance

**8 Tables Total:**

| Table | Purpose | Key Columns | Relationships |
|-------|---------|-------------|---------------|
| `user_settings` | App preferences | theme, retention_limit | - |
| `broker_accounts` | Broker info | broker_name, last_upload | → snapshots |
| `portfolio_snapshots` | Per-broker data | total_value, csv_filename | ← broker, → holdings |
| `aggregate_snapshots` | Combined view | total_value (all brokers) | ↔ snapshots, → risk |
| `holdings` | Individual positions | symbol, quantity, value | ← snapshot |
| `underlying_holdings` | ETF/MF breakdown | symbol, percentage | ← aggregate |
| `risk_metrics` | Risk analysis | concentrated, overlapping | ← aggregate |
| `aggregate_portfolio_association` | M:N join table | - | snapshots ↔ aggregates |

---

## 🎯 Key Features

### 1. **Multi-Broker Support**
```python
brokers = ['merrill', 'fidelity', 'webull', 'robinhood', 'schwab']
```
Each broker can have multiple snapshots over time.

### 2. **JSON Flexibility**
```python
# Store complex nested data without additional tables
holding.underlying_holdings_list = [
    {'symbol': 'AAPL', 'weight': 0.05, 'value': 1000},
    # ...
]
```

### 3. **Cascade Deletes**
```python
# Delete broker → automatically deletes snapshots → automatically deletes holdings
session.delete(broker)
```

### 4. **Property Helpers**
```python
# Access JSON as Python objects
concentrated = risk.concentrated_stocks_list  # Returns list
sectors = risk.sector_breakdown_dict  # Returns dict
```

### 5. **SQLite WAL Mode**
- Better concurrency
- Prevents "database is locked" errors
- Automatic in `database.py`

---

## 🚀 How to Use

### 1. Initialize Database

**From Docker (Recommended):**
```bash
docker-compose up -d
docker-compose exec app python scripts/init_db.py
```

**From Host:**
```bash
export DATABASE_URL=sqlite:///data/portfolio.db
python scripts/init_db.py
```

### 2. Verify Database

```bash
# Check file exists
ls -lh data/portfolio.db

# Check tables
sqlite3 data/portfolio.db ".tables"

# Expected output:
# aggregate_portfolio_association  holdings
# aggregate_snapshots              portfolio_snapshots
# broker_accounts                  risk_metrics
#                                  underlying_holdings
#                                  user_settings
```

### 3. Test Database Access

```python
# In Python shell or script
from app.database import get_session
from app.models import BrokerAccount

session = get_session()
brokers = session.query(BrokerAccount).all()
print(f"Found {len(brokers)} broker accounts")
session.close()
```

---

## 📊 Data Flow Example

### Creating a Portfolio Snapshot

```python
from app.database import db_session
from app.models import BrokerAccount, PortfolioSnapshot, Holding
from datetime import datetime
from decimal import Decimal

with db_session() as session:
    # 1. Create or get broker account
    broker = BrokerAccount(
        broker_name='merrill',
        account_number_last4='1234',
        last_uploaded_at=datetime.utcnow()
    )
    session.add(broker)
    session.flush()  # Get ID
    
    # 2. Create portfolio snapshot
    snapshot = PortfolioSnapshot(
        broker_account_id=broker.id,
        snapshot_date=datetime.utcnow(),
        total_value=Decimal('100000.00'),
        total_positions=2,
        csv_filename='merrill_20260125.csv'
    )
    session.add(snapshot)
    session.flush()
    
    # 3. Add holdings
    holdings = [
        Holding(
            portfolio_snapshot_id=snapshot.id,
            symbol='AAPL',
            name='Apple Inc.',
            quantity=Decimal('100'),
            price=Decimal('175.50'),
            total_value=Decimal('17550.00'),
            asset_type='stock'
        ),
        Holding(
            portfolio_snapshot_id=snapshot.id,
            symbol='VTI',
            name='Vanguard Total Stock Market ETF',
            quantity=Decimal('200'),
            price=Decimal('250.00'),
            total_value=Decimal('50000.00'),
            asset_type='etf'
        )
    ]
    
    for holding in holdings:
        session.add(holding)
    
    # Auto-commits on context exit
```

---

## ✅ Testing Checklist

Phase 2 is complete when:

- [ ] `data/portfolio.db` file exists and is ~100KB+
- [ ] 8 tables created (verify with `.tables` in SQLite)
- [ ] `user_settings` has 1 row with default values
- [ ] Can create `BrokerAccount` via Python
- [ ] Can create `PortfolioSnapshot` with `Holdings`
- [ ] Relationships work (broker.portfolio_snapshots)
- [ ] JSON fields serialize/deserialize correctly
- [ ] Cascade delete works (delete broker → snapshots gone)
- [ ] No errors in `docker-compose logs app`

**Run All Tests:**
```bash
# From container
docker-compose exec app python -c "
from app.database import init_db
init_db()
print('✅ Database initialized')
"

# Test CRUD
docker-compose exec app python scripts/init_db.py
# Answer 'yes' to create sample data
# Verify sample data appears
```

---

## 🐛 Common Issues

### Issue: "no such table: broker_accounts"
**Solution:**
```bash
docker-compose exec app python scripts/init_db.py
```

### Issue: "database is locked"
**Solution:** Restart app container
```bash
docker-compose restart app
```

### Issue: Permission denied on data/
**Solution:**
```bash
sudo chown -R 1000:1000 data/
chmod 700 data/
```

### Issue: Can't import app.database
**Solution:** Verify you're running from correct directory
```bash
docker-compose exec app python -c "import app.database; print('OK')"
```

---

## 📈 Next Phase Preview

**Phase 3: CSV Upload (Merrill Lynch)**

What we'll build:
1. File upload route (`/upload`)
2. Drag-and-drop UI with broker cards
3. Merrill Lynch CSV parser
4. Validation and error handling
5. Store parsed data in database
6. Update dashboard to show broker cards

Files we'll create:
- `app/routes/upload.py`
- `app/services/csv_parser_base.py`
- `app/services/merrill_csv_parser.py`
- `app/templates/dashboard.html` (update)
- `app/templates/components/broker_card.html`

---

## 📚 Resources

- **SQLAlchemy Docs**: https://docs.sqlalchemy.org/
- **SQLite Docs**: https://www.sqlite.org/docs.html
- **Database Browser**: https://sqlitebrowser.org/ (GUI for SQLite)

---

## 🎓 Key Learnings

### Why SQLite?
- Perfect for single-user, localhost deployment
- Zero configuration
- One file = entire database
- Fast and reliable
- Easy backups (just copy the file)

### Why SQLAlchemy?
- Pythonic interface to SQL
- Prevents SQL injection
- Easy migrations (Alembic)
- Database-agnostic (easy to switch to PostgreSQL later)

### Why JSON in SQLite?
- Flexible schema for variable data
- No need for many-to-many tables for lists
- Easy to query and update
- SQLite 3.38+ has JSON functions

### Why WAL Mode?
- Better concurrency (multiple readers + 1 writer)
- Fewer "database is locked" errors
- Better for web apps
- Slight overhead but worth it

---

**Ready to proceed to Phase 3?** 🚀