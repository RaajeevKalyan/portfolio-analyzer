# Phase 3: CSV Upload (Merrill Lynch)

## ✅ What We're Building

This phase implements CSV upload functionality:
- **Upload route** - `/upload` endpoint with file handling
- **Merrill Lynch CSV parser** - Flexible parser for Merrill CSV formats
- **Dashboard UI** - Broker cards with drag-and-drop upload
- **Data storage** - Save parsed CSV data to database
- **Real-time feedback** - Loading states and success/error messages

## 📦 Files Created

### Backend (6 files)
```
app/services/
├── __init__.py                # Services package init
├── csv_parser_base.py         # Abstract base class for parsers
└── merrill_csv_parser.py      # Merrill Lynch CSV parser

app/routes/
├── __init__.py                # Routes package init
└── upload.py                  # File upload handling

app/main.py (updated)          # Register upload blueprint, new dashboard route
```

### Frontend (1 file)
```
app/templates/
└── dashboard.html             # Dashboard with broker cards
```

### Documentation (1 file)
```
PHASE3_CSV_UPLOAD.md          # This file
```

## 🎯 Features Implemented

### 1. CSV Parser Base Class
**File**: `app/services/csv_parser_base.py`

**Provides:**
- Abstract methods for validation and parsing
- Currency cleaning (`$1,234.56` → `Decimal('1234.56')`)
- Quantity cleaning (handles commas)
- Asset type detection (stock vs ETF vs mutual fund vs bond vs cash)
- Symbol normalization
- Column finding (case-insensitive, flexible matching)

### 2. Merrill Lynch Parser
**File**: `app/services/merrill_csv_parser.py`

**Handles:**
- Multiple Merrill CSV format variations
- Flexible column matching (Symbol/Ticker, Quantity/Shares, Value/Market Value)
- Account number extraction
- Price calculation if not provided
- Asset type detection based on symbol and description

**Supported CSV Columns** (flexible):
- Symbol (or Ticker, Security)
- Description (or Security Description, Name)
- Quantity (or Shares, Qty)
- Price (or Last Price, Market Price) - optional
- Value (or Market Value, Total Value)
- Account Type (optional)

### 3. Upload Endpoint
**File**: `app/routes/upload.py`

**POST /upload**
- Accepts: multipart/form-data with `file` and `broker`
- Validates file type (.csv only)
- Validates broker name
- Saves file temporarily
- Parses CSV
- Stores in database
- Returns JSON response

**Response Format:**
```json
{
  "success": true,
  "message": "Successfully uploaded 25 positions",
  "data": {
    "broker_name": "merrill",
    "total_value": 125000.50,
    "total_positions": 25,
    "snapshot_id": 1,
    "account_last4": "1234"
  }
}
```

### 4. Dashboard UI
**File**: `app/templates/dashboard.html`

**Features:**
- **5 Broker Cards** (Merrill, Fidelity, Webull, Robinhood, Schwab)
- **Drag-and-Drop Upload** - Drop CSV onto card
- **Click to Upload** - Traditional file picker
- **Loading States** - Spinner while processing
- **Success/Error Alerts** - Floating notifications
- **Data Display** - Shows net worth, positions, last updated
- **Font Awesome Icons** - Color-coded per broker
- **Responsive Grid** - Auto-fits to screen size

**Broker Colors:**
- Merrill Lynch: Red (#CC0000) 🏛️
- Fidelity: Green (#00783E) 📈
- Webull: Purple (#5B21B6) 📊
- Robinhood: Green (#00C805) 📈
- Schwab: Blue (#00A0DC) 🏛️

## 🚀 Testing Phase 3

### Prerequisites

1. **Containers running** with Phase 2 database initialized:
```bash
docker-compose up -d
docker-compose exec app python scripts/init_db.py
# Answer 'no' to sample data (we'll use real CSV)
```

2. **Merrill Lynch CSV file** ready to upload

---

### Test 1: Access Dashboard

```bash
# Open browser
open https://localhost:8443
```

**Expected:**
- Dashboard with 5 broker cards
- Total Net Worth: $0.00
- All cards show "Drop CSV here" upload zones
- Colored icons for each broker

---

### Test 2: Upload Merrill Lynch CSV

#### Option A: Drag and Drop
1. Open your Merrill Lynch CSV file in Finder/Explorer
2. Drag the CSV onto the **Merrill Lynch** broker card
3. Drop it on the upload zone

#### Option B: Click to Upload
1. Click on the Merrill Lynch card
2. Select your CSV file from file picker
3. Click "Open"

**Expected Behavior:**
1. Card shows loading spinner: "Uploading and processing CSV..."
2. After 2-5 seconds: Success alert appears (green)
3. Page auto-refreshes after 1.5 seconds
4. Merrill card now shows:
   - Total value (e.g., $267,000.45)
   - Number of positions (e.g., 25 positions)
   - Account ***1234
   - Last updated timestamp
   - "Update CSV" button

**Check Database:**
```bash
docker-compose exec app python -c "
from app.database import get_session
from app.models import BrokerAccount, PortfolioSnapshot, Holding

session = get_session()

broker = session.query(BrokerAccount).filter_by(broker_name='merrill').first()
print(f'Broker: {broker.broker_name}, Account: ***{broker.account_number_last4}')

snapshot = session.query(PortfolioSnapshot).filter_by(broker_account_id=broker.id).first()
print(f'Snapshot: {snapshot.total_positions} positions, ${snapshot.total_value}')

holdings = session.query(Holding).filter_by(portfolio_snapshot_id=snapshot.id).all()
for holding in holdings[:5]:  # Print first 5
    print(f'  {holding.symbol}: {holding.quantity} @ ${holding.price} = ${holding.total_value}')

session.close()
"
```

---

### Test 3: Invalid File Handling

**Test 3a: Wrong File Type**
1. Try uploading a .txt or .xlsx file
2. **Expected**: Error alert "Invalid file type. Only CSV files are allowed."

**Test 3b: Empty File**
1. Create an empty CSV file
2. Upload it
3. **Expected**: Error alert "CSV file is empty"

**Test 3c: Invalid CSV Format**
1. Create CSV with wrong columns
2. Upload it
3. **Expected**: Error alert "Invalid CSV format: Missing required columns..."

---

### Test 4: Multiple Uploads (Update Data)

1. Upload Merrill CSV (if not already done)
2. Wait for success
3. Upload the SAME Merrill CSV again (or a modified version)

**Expected:**
- Creates NEW snapshot (doesn't delete old one)
- Updates "Last updated" timestamp
- Shows latest total value
- Old snapshot still in database (for historical tracking)

**Verify:**
```bash
docker-compose exec app python -c "
from app.database import get_session
from app.models import BrokerAccount, PortfolioSnapshot

session = get_session()

broker = session.query(BrokerAccount).filter_by(broker_name='merrill').first()
snapshots = session.query(PortfolioSnapshot).filter_by(broker_account_id=broker.id).all()

print(f'Broker has {len(snapshots)} snapshots:')
for i, snapshot in enumerate(snapshots, 1):
    print(f'  {i}. {snapshot.snapshot_date}: ${snapshot.total_value}')

session.close()
"
```

---

### Test 5: Upload to Different Broker (Using Same CSV)

**Purpose**: Test that wrong broker detection works

1. Upload your Merrill CSV to **Fidelity** card

**Expected**: 
- Should still work! (Parser is flexible)
- Data stored under Fidelity broker
- This is OK for testing - in production, users upload correct CSV to correct card

---

### Test 6: Check Logs

```bash
# View upload logs
docker-compose logs app | grep -i upload

# Should see lines like:
# INFO - Uploaded file saved: /app/uploads/merrill_20260125_143022_portfolio.csv
# INFO - Merrill CSV validation passed: 25 rows
# INFO - Parsed 25 holdings, total value: $267000.45
# INFO - Created new broker account: merrill (***1234)
# INFO - Created snapshot 1 for merrill: $267000.45, 25 positions
```

---

### Test 7: Asset Type Detection

Check that asset types are correctly identified:

```bash
docker-compose exec app python -c "
from app.database import get_session
from app.models import Holding
from sqlalchemy import func

session = get_session()

# Count by asset type
asset_counts = session.query(
    Holding.asset_type,
    func.count(Holding.id)
).group_by(Holding.asset_type).all()

print('Holdings by Asset Type:')
for asset_type, count in asset_counts:
    print(f'  {asset_type}: {count}')

# Show some examples
stocks = session.query(Holding).filter_by(asset_type='stock').limit(3).all()
print('
Sample Stocks:')
for holding in stocks:
    print(f'  {holding.symbol} ({holding.name})')

etfs = session.query(Holding).filter_by(asset_type='etf').limit(3).all()
print('
Sample ETFs:')
for holding in etfs:
    print(f'  {holding.symbol} ({holding.name})')

session.close()
"
```

---

## 📊 Sample Merrill Lynch CSV Formats

### Format 1: Standard Export
```csv
Symbol,Description,Quantity,Price,Market Value,Account Type
AAPL,Apple Inc.,100,175.50,17550.00,Individual
VTI,Vanguard Total Stock Market ETF,200,250.00,50000.00,IRA
MSFT,Microsoft Corporation,150,380.00,57000.00,Individual
```

### Format 2: With Account Column
```csv
Account,Symbol,Security Description,Shares,Last Price,Total Value
XXX-1234,AAPL,APPLE INC,100,$175.50,"$17,550.00"
XXX-1234,VTI,VANGUARD TOTAL STK MKT,200,$250.00,"$50,000.00"
```

### Format 3: Minimal
```csv
Ticker,Qty,Value
AAPL,100,17550
VTI,200,50000
MSFT,150,57000
```

**Parser handles all formats!** It flexibly matches column names.

---

## 🔍 How It Works (Under the Hood)

### 1. Upload Flow
```
User drops CSV on card
   ↓
JavaScript: handleDrop()
   ↓
JavaScript: uploadFile() → POST /upload
   ↓
Flask: upload_bp.route('/upload')
   ↓
Validate file (.csv only)
   ↓
Save to /app/uploads/
   ↓
MerrillCSVParser.validate_csv()
   ↓
MerrillCSVParser.parse_csv()
   ↓
store_portfolio_data() → Database
   ↓
Return JSON response
   ↓
JavaScript: Show success, reload page
```

### 2. Parsing Flow
```
Load CSV with pandas
   ↓
Strip whitespace from column names
   ↓
Map columns (Symbol→symbol, Quantity→quantity, etc.)
   ↓
For each row:
   ↓
   Extract symbol (normalize to uppercase)
   ↓
   Clean quantity (remove commas)
   ↓
   Clean currency (remove $, commas, handle negatives)
   ↓
   Calculate price (if not provided)
   ↓
   Detect asset type (stock/etf/mutual_fund/etc.)
   ↓
   Create holding dict
   ↓
Return parsed data
```

### 3. Storage Flow
```
Get or create BrokerAccount
   ↓
Update last_uploaded_at timestamp
   ↓
Create PortfolioSnapshot
   ↓
For each holding:
   ↓
   Create Holding record
   ↓
Commit transaction
   ↓
Return snapshot_id
```

---

## ✅ Success Criteria

Phase 3 is complete if:

- [ ] Dashboard loads at `https://localhost:8443`
- [ ] Shows 5 broker cards (Merrill, Fidelity, Webull, Robinhood, Schwab)
- [ ] Can drag-and-drop CSV onto Merrill card
- [ ] Can click card to open file picker
- [ ] Loading spinner appears during upload
- [ ] Success message shows after upload
- [ ] Page auto-refreshes
- [ ] Merrill card shows total value and positions
- [ ] Data stored in database correctly
- [ ] Can upload multiple times (creates multiple snapshots)
- [ ] Total Net Worth updates correctly
- [ ] Invalid files show error messages
- [ ] No errors in `docker-compose logs app`

---

## 🐛 Troubleshooting

### Issue: Upload button doesn't work

**Check:**
```bash
# Verify Flask app has upload route registered
docker-compose exec app python -c "
from app.main import create_app
app = create_app()
print('Routes:', [str(rule) for rule in app.url_map.iter_rules()])
"
# Should see: /upload
```

### Issue: CSV parsing fails

**Debug:**
```bash
# Check CSV format manually
head -20 your_file.csv

# Test parser directly
docker-compose exec app python -c "
from app.services.merrill_csv_parser import MerrillCSVParser

parser = MerrillCSVParser()
is_valid, error = parser.validate_csv('/path/to/your.csv')
print(f'Valid: {is_valid}, Error: {error}')
"
```

### Issue: File upload fails with 413 error

**Solution:** File too large (>10MB limit)
```bash
# Check file size
ls -lh your_file.csv

# If needed, increase limit in .env:
MAX_UPLOAD_SIZE=20971520  # 20MB
```

### Issue: Drag-and-drop doesn't work

**Check:** 
- Using modern browser (Chrome, Firefox, Safari)
- JavaScript not blocked
- Check browser console for errors (F12)

---

## 📈 Next Steps

**Phase 4: Additional Broker Parsers**

We'll add parsers for:
1. Fidelity CSV format
2. Webull CSV format
3. Robinhood CSV format
4. Schwab CSV format

Each broker has different CSV formats, but we'll follow the same pattern as Merrill.

**Phase 5: Risk Analysis**

After we can upload CSVs from all brokers:
1. Parse ETF/MF underlying holdings (mstarpy)
2. Aggregate holdings across brokers
3. Calculate risk metrics
4. Display risk alerts on dashboard

---

## 📝 Notes

- **Uploaded files** are kept in `/app/uploads/` for debugging
- **File naming**: `{broker}_{timestamp}_{original_filename}.csv`
- **Account number** extracted from CSV if available (last 4 digits)
- **Multiple snapshots** are intentional (historical tracking)
- **Asset type detection** is heuristic-based (can be refined)
- **Price calculation**: If price not in CSV, calculated as value ÷ quantity

---

**Phase 3 complete!** You now have a working CSV upload system for Merrill Lynch. Test it with your real CSV file and verify the data appears correctly in the database and dashboard! 🎉