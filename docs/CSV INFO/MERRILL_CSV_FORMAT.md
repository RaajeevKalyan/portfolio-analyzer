# Merrill Lynch CSV Format Guide

## 📄 Merrill CSV Structure

Merrill Lynch exports have a **complex multi-section format**:

### Section 1: Account Summary (Skip)
```
, "IRRA-Edge 43X-40L72" ,"Value" ,"Day's Value Change" ,"Unrealized Gain/Loss"  
"" ,"$10.45" ,"$0.00 0.00%" ,"+$2.45 +54.75%"  
"Short-term gain" ,"+$377.46" 
...
```
This section is enclosed in single quotes or has comma-prefixed lines.

### Section 2: Holdings Data (Extract This!)
```
""
"Symbol " ,"Description" ,"Day's Price $ Chg % Chg" ,"Quantity" ,"Day's Value Change $" ,"Value" ,"Unrealized Gain/Loss $ Chg % Chg" ,"Price"
"AMD" ,"ADVNCD MICRO D INC" ,"$0.00 0.00%" ,"5" ,"$0.00" ,"$14,80.76" ,"+$9,83.36 +197.80%" ,"$259.68"
"AAPL" ,"APPLE INC" ,"$0.00 0.00%" ,"10" ,"$0.00" ,"$2,500.00" ,"+$500.00 +25.00%" ,"$250.00"
""
```
This section is enclosed in double quotes `""...""`.

### Section 3: Footer (Skip)
Additional summary information.

---

## 🔧 How the Parser Handles This

### 1. Extract Data Section
```python
# Find content between "" and ""
pattern = r'""[\s\n]*(.*?)[\s\n]*""'
matches = re.findall(pattern, content, re.DOTALL)

# Take the largest match (usually the holdings data)
data_section = max(matches, key=len)
```

### 2. Parse as Normal CSV
Once extracted, the data section is a standard CSV:
```
Symbol,Description,Quantity,Value,Price
AMD,ADVNCD MICRO D INC,5,$14,80.76,$259.68
```

### 3. Handle Number Formats
Merrill has **inconsistent number formatting**:
- Standard: `$1,480.76`
- Weird: `$14,80.76` (comma in wrong place!)
- With percentages: `$0.00 0.00%`

**Parser fixes:**
```python
# Extract just numbers from complex strings
"$0.00 0.00%" → "0.00"

# Fix misplaced commas
"$14,80.76" → "$1480.76"

# Handle parentheses (negative)
"($123.45)" → "-123.45"
```

---

## 📋 Required Columns (Flexible Matching)

The parser looks for these columns (case-insensitive):

| Standard | Merrill Variations |
|----------|-------------------|
| **Symbol** | Symbol, Ticker, Security |
| **Description** | Description, Security Description, Name |
| **Quantity** | Quantity, Shares, Qty |
| **Value** | Value, Market Value, Total Value, Current Value |
| **Price** | Price, Last Price, Market Price, Unit Price (optional) |

---

## 🧪 Testing Your CSV

### Check CSV Structure
```bash
# View first 30 lines
head -30 your_merrill_file.csv

# Look for:
# 1. Account number in header (e.g., "IRRA-Edge 43X-40L72")
# 2. Data section between ""..."" 
# 3. Columns: Symbol, Description, Quantity, Value
```

### Test Parser Directly
```bash
docker-compose exec app python -c "
from app.services.merrill_csv_parser import MerrillCSVParser

parser = MerrillCSVParser()

# Validate
is_valid, error = parser.validate_csv('/app/uploads/your_file.csv')
print(f'Valid: {is_valid}')
if not is_valid:
    print(f'Error: {error}')

# Parse
if is_valid:
    data = parser.parse_csv('/app/uploads/your_file.csv')
    print(f'Total Value: \${data[\"total_value\"]}')
    print(f'Holdings: {len(data[\"holdings\"])}')
    print(f'Account: ***{data[\"account_number_last4\"]}')
    
    # Show first 3 holdings
    for i, h in enumerate(data['holdings'][:3], 1):
        print(f'{i}. {h[\"symbol\"]}: {h[\"quantity\"]} @ \${h[\"price\"]} = \${h[\"total_value\"]}')
"
```

---

## 🐛 Common Issues & Fixes

### Issue 1: "Could not find Symbol/Ticker column"

**Cause**: Data section not extracted properly

**Debug:**
```bash
# Check if CSV has quoted sections
grep '""' your_file.csv

# Expected: Should find "" at start and end of data section
```

**Fix**: 
- Ensure CSV has the `""` markers
- Try downloading CSV again from Merrill website

---

### Issue 2: "CSV file is empty"

**Cause**: No data between `""` markers

**Debug:**
```python
# Manually check file structure
with open('your_file.csv', 'r') as f:
    content = f.read()
    print('Has double quotes:', '""' in content)
    print('Content length:', len(content))
```

**Fix**: 
- Verify CSV downloaded completely
- Check file isn't corrupted

---

### Issue 3: Wrong Total Value

**Cause**: Number format parsing issues

**Debug:**
```bash
# Check specific value in CSV
grep "AMD" your_file.csv

# Look at the Value column - is it formatted correctly?
# "$14,80.76" ← Comma in wrong place!
# "$1,480.76" ← Correct format
```

**Fix**: Parser now handles both formats automatically

---

### Issue 4: Account Number Not Extracted

**Cause**: Account number in unexpected format

**Debug:**
```bash
# Check first 10 lines for account info
head -10 your_file.csv | grep -E "[A-Z0-9]{3,4}-[A-Z0-9]+"
```

**Fix**: 
- Parser looks for patterns like `IRRA-Edge 43X-40L72`
- If not found, will use None (account shown as "***None")
- Can manually set account nickname later

---

## 📝 Example Merrill CSV

Here's what a typical Merrill export looks like:

```csv
, "IRRA-Edge 43X-40L72" ,"Value" ,"Day's Value Change" ,"Unrealized Gain/Loss"  
"" ,"$10,480.76" ,"$0.00 0.00%" ,"+$2,450.45 +30.50%"  

""
"Symbol " ,"Description" ,"Day's Price $ Chg % Chg" ,"Quantity" ,"Day's Value Change $" ,"Value" ,"Unrealized Gain/Loss $ Chg % Chg" ,"Price"
"AMD" ,"ADVANCED MICRO DEVICES INC" ,"$0.00 0.00%" ,"5" ,"$0.00" ,"$1,480.76" ,"+$983.36 +197.80%" ,"$296.15"
"AAPL" ,"APPLE INC" ,"$0.00 0.00%" ,"10" ,"$0.00" ,"$2,500.00" ,"+$500.00 +25.00%" ,"$250.00"
"VTI" ,"VANGUARD TOTAL STOCK MARKET" ,"$0.00 0.00%" ,"30" ,"$0.00" ,"$6,500.00" ,"+$967.09 +17.50%" ,"$216.67"
""

"Total Value:" ,"$10,480.76"
```

**Parser extracts:**
- Account: `40L72` (last 4 of `43X-40L72`)
- 3 holdings (AMD, AAPL, VTI)
- Total: $10,480.76

---

## ✅ Success Checklist

Your CSV should work if:
- [ ] Has `""` markers around data section
- [ ] Has Symbol column
- [ ] Has Quantity column  
- [ ] Has Value column
- [ ] Holdings have non-zero values
- [ ] File size > 1KB
- [ ] Opens in Excel/Sheets without errors

---

## 🔄 If Parser Still Fails

**Option 1: Share CSV Format**
Save first 30 lines (with sensitive data removed):
```bash
head -30 your_file.csv > sample.csv
# Remove account numbers, replace with XXX
# Share sample.csv for debugging
```

**Option 2: Manual CSV Creation**
Create a simple CSV manually:
```csv
Symbol,Description,Quantity,Value,Price
AAPL,Apple Inc.,10,2500.00,250.00
MSFT,Microsoft Corp.,5,1900.00,380.00
VTI,Vanguard Total Stock Market,30,6500.00,216.67
```

Upload this to test the system works.

**Option 3: Check Logs**
```bash
docker-compose logs app | tail -50

# Look for specific error messages
# Parser logs detailed info about what went wrong
```

---

## 💡 Tips

1. **Download fresh CSV** - Merrill format may change over time
2. **Use "Positions" export** - Not "Transactions" or "History"
3. **Export from main portfolio page** - Not individual accounts
4. **Check file encoding** - Should be UTF-8
5. **No manual edits** - Upload original Merrill export

---

**If your CSV still doesn't parse after these steps, share the error message and first 20 lines (with sensitive data masked) for further debugging.**