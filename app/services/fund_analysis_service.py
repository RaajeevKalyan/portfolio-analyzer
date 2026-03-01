"""
Fund Analysis Service - Expense Ratio and Peer Comparison

Analyzes ETF and Mutual Fund holdings for:
1. Expense ratio analysis with annual cost calculation
2. Category-based peer comparison using Morningstar Medalist ratings
3. Historical performance comparison using NAV data

Uses yfinance for expense ratio (more reliable) and mstarpy 8.0.3 for ratings/peers.
"""
import logging
import mstarpy as ms
import yfinance as yf
import pandas as pd
from typing import List, Dict, Optional, Tuple
from decimal import Decimal
from datetime import datetime, timedelta
from dataclasses import dataclass
import json
from pathlib import Path

logger = logging.getLogger(__name__)

# Cache for fund data to avoid repeated API calls
FUND_CACHE_FILE = Path('/app/data/fund_analysis_cache.json')


@dataclass
class FundExpenseInfo:
    """Fund expense information"""
    symbol: str
    name: str
    category: str
    category_id: str
    expense_ratio: float  # As decimal (0.0003 = 0.03%)
    portfolio_value: float
    annual_expense: float
    medalist_rating: str
    star_rating: int
    return_m12: float  # 12 month return
    security_id: str


@dataclass
class PeerFund:
    """Peer fund information"""
    security_id: str
    name: str
    ticker: str
    expense_ratio: float
    medalist_rating: str
    star_rating: int
    return_m12: float
    return_m36: float
    return_m60: float
    fund_size: float


class FundAnalysisService:
    """Service for fund expense and peer analysis"""
    
    # Medalist ratings in order of preference
    MEDALIST_RATINGS = ['Gold', 'Silver', 'Bronze', 'Neutral', 'Negative']
    
    def __init__(self):
        self.cache = self._load_cache()
    
    def _load_cache(self) -> Dict:
        """Load fund analysis cache"""
        try:
            if FUND_CACHE_FILE.exists():
                with open(FUND_CACHE_FILE, 'r') as f:
                    return json.load(f)
        except Exception as e:
            logger.warning(f"Error loading fund cache: {e}")
        return {}
    
    def _save_cache(self):
        """Save fund analysis cache"""
        try:
            FUND_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(FUND_CACHE_FILE, 'w') as f:
                json.dump(self.cache, f, indent=2)
        except Exception as e:
            logger.warning(f"Error saving fund cache: {e}")
    
    def _get_expense_ratio_yfinance(self, symbol: str) -> Tuple[float, str]:
        """
        Get expense ratio from yfinance funds_data
        
        Returns:
            Tuple of (expense_ratio as decimal e.g. 0.0131 for 1.31%, category name)
            
        Note: yfinance returns expense ratios inconsistently:
              - ETFs often return decimal (0.0003 for 0.03%)
              - Mutual funds often return percentage (1.31 for 1.31%)
              We detect based on realistic expense ratio ranges.
        """
        logger.info(f"  [yfinance] Fetching expense ratio for {symbol}...")
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info or {}
            category = info.get('category', '')
            logger.info(f"  [yfinance] {symbol} category: {category}")
            
            def normalize_expense_ratio(raw_value: float, source: str) -> float:
                """
                Normalize expense ratio to decimal format.
                
                yfinance behavior varies by API method:
                - info dict: Usually decimal (0.0003 = 0.03%)
                - funds_data: Can be percentage (0.03 = 0.03%) or decimal
                
                Real expense ratios range from 0.01% to 3%:
                - In decimal: 0.0001 to 0.03
                - In percentage: 0.01 to 3.0
                
                Strategy based on realistic ranges:
                - If value > 1.0: definitely percentage (e.g., 1.06 = 1.06%), divide by 100
                - If value >= 0.05: likely percentage (e.g., 0.5 = 0.5%), divide by 100
                - If value < 0.05: could be either, but assume decimal for safety
                  (0.03 as decimal = 3%, which is high but possible for some MFs)
                  (0.0003 as decimal = 0.03%, which is correct for VOO)
                
                Note: This is imperfect - 0.03 could mean 0.03% or 3%.
                We rely on mstarpy as primary source which is more consistent.
                """
                if raw_value <= 0:
                    return 0
                
                logger.info(f"    {symbol} [{source}]: raw = {raw_value}")
                
                # Clear percentage format: >= 0.05 or > 1.0
                if raw_value >= 0.05:
                    result = raw_value / 100
                    logger.info(f"    {symbol}: {raw_value} -> {result} (÷100, was percentage format)")
                    return result
                else:
                    # Value < 0.05: likely already decimal
                    # 0.0003 = 0.03%, 0.03 = 3%
                    logger.info(f"    {symbol}: {raw_value} -> {raw_value} (kept, assumed decimal)")
                    return raw_value
            
            # Method 1: Try funds_data (newer yfinance API)
            try:
                funds_data = ticker.funds_data
                if funds_data:
                    # Get expense ratio from fund_operations
                    try:
                        fund_ops = funds_data.fund_operations
                        if fund_ops is not None and hasattr(fund_ops, 'empty') and not fund_ops.empty:
                            expense_fields = [
                                'Annual Report Expense Ratio (net)',
                                'Annual Report Net Expense Ratio', 
                                'Total Expense Ratio',
                                'Expense Ratio (net)',
                                'Net Expense Ratio',
                                'Gross Expense Ratio',
                                'annualReportExpenseRatio'
                            ]
                            
                            for field in expense_fields:
                                if field in fund_ops.index:
                                    val = fund_ops.loc[field]
                                    if hasattr(val, 'iloc'):
                                        val = val.iloc[0] if len(val) > 0 else None
                                    elif hasattr(val, 'values'):
                                        val = val.values[0] if len(val.values) > 0 else None
                                    
                                    if val is not None and pd.notna(val):
                                        raw = float(val)
                                        expense = normalize_expense_ratio(raw, f"fund_ops.{field}")
                                        logger.info(f"  yfinance expense for {symbol}: {expense} ({expense*100:.4f}%)")
                                        return expense, category
                        
                        if isinstance(fund_ops, dict):
                            for field in ['annualReportExpenseRatio', 'totalExpenseRatio', 'netExpenseRatio']:
                                if field in fund_ops and fund_ops[field]:
                                    raw = float(fund_ops[field])
                                    expense = normalize_expense_ratio(raw, f"fund_ops_dict.{field}")
                                    return expense, category
                                    
                    except Exception as e:
                        logger.debug(f"  fund_operations parsing error for {symbol}: {e}")
                    
                    try:
                        overview = funds_data.fund_overview
                        if overview and isinstance(overview, dict):
                            for field in ['expenseRatio', 'netExpenseRatio', 'annualReportExpenseRatio']:
                                if field in overview and overview[field]:
                                    raw = float(overview[field])
                                    expense = normalize_expense_ratio(raw, f"fund_overview.{field}")
                                    return expense, category
                    except Exception as e:
                        logger.debug(f"  fund_overview error for {symbol}: {e}")
                        
            except Exception as e:
                logger.debug(f"  funds_data not available for {symbol}: {e}")
            
            # Method 2: Try info dict (fallback)
            expense_info_fields = [
                'annualReportExpenseRatio', 
                'expenseRatio', 
                'netExpenseRatio', 
                'totalExpenseRatio',
            ]
            
            for field in expense_info_fields:
                if field in info and info[field] is not None:
                    raw = float(info[field])
                    expense = normalize_expense_ratio(raw, f"info.{field}")
                    if expense > 0:
                        logger.info(f"  yfinance info expense for {symbol}: {expense} ({expense*100:.4f}%)")
                        return expense, category
            
            return 0, category
                
        except Exception as e:
            logger.warning(f"Error getting yfinance data for {symbol}: {e}")
        
        return 0, ''
    
    def _search_fund(self, symbol: str) -> Optional[Dict]:
        """
        Search for a fund by symbol and get its details
        Returns fund info including category, expense ratio, etc.
        
        Uses mstarpy ongoingCharge as PRIMARY source (more reliable/consistent),
        yfinance as fallback.
        """
        symbol = symbol.upper().strip()
        
        # Check cache first
        cache_key = f"fund_{symbol}"
        if cache_key in self.cache:
            cached = self.cache[cache_key]
            # Cache valid for 24 hours
            if cached.get('timestamp', 0) > (datetime.now().timestamp() - 86400):
                logger.debug(f"Using cached data for {symbol}")
                return cached.get('data')
        
        logger.info(f"Looking up fund data for {symbol}...")
        
        # STEP 1: Get data from mstarpy (PRIMARY source for expense ratio)
        us_exchanges = ["ARCX", "XNAS", "XNYS", "BATS", "NYSE", "NASDAQ"]
        mstar_data = None
        mstar_expense = 0
        
        for inv_type in ["FE", "FO"]:  # ETF, Mutual Fund
            try:
                logger.info(f"  [mstarpy] Searching for {symbol} as {inv_type}...")
                results = ms.screener_universe(
                    symbol,
                    language="en-gb",
                    field=[
                        "name", "ticker", "exchange", "morningstarCategory",
                        "ongoingCharge", "fundStarRating", "medalistRating",
                        "totalReturn", "fundSize"
                    ],
                    filters={"investmentType": inv_type},
                    pageSize=50
                )
                
                logger.info(f"  [mstarpy] Found {len(results) if results else 0} results for {symbol}")
                
                if results:
                    for result in results:
                        meta = result.get("meta", {})
                        fields = result.get("fields", {})
                        
                        ticker = meta.get("ticker", "") or ""
                        exchange = meta.get("exchange", "") or ""
                        
                        if ticker.upper() == symbol and exchange in us_exchanges:
                            logger.info(f"  [mstarpy] MATCH: {ticker} on {exchange}")
                            # Get mstarpy expense ratio (ongoingCharge)
                            # mstarpy ongoingCharge can be:
                            # - 0.03 meaning 0.03% (common for ETFs like VOO)
                            # - 3.0 meaning 3% (if returned in raw percentage)
                            raw_mstar_expense = self._get_field_value(fields, "ongoingCharge", 0)
                            if raw_mstar_expense:
                                logger.info(f"  [mstarpy] ongoingCharge for {symbol}: {raw_mstar_expense}")
                                
                                # Normalize: if value >= 1, it's already percentage form (e.g., 3.0 = 3%)
                                # If value < 1, it could be either:
                                #   - 0.03 meaning 0.03% (percentage form)
                                #   - 0.03 meaning 3% (decimal form, needs no change)
                                # 
                                # Key insight: VOO has ER of 0.03%, so if we see 0.03, it's percentage
                                # No ETF has 0.03 decimal ER (that would be 3%)
                                #
                                # Strategy: assume values are in percentage format (0.03 = 0.03%)
                                # Only divide by 100 to convert to decimal
                                mstar_expense = raw_mstar_expense / 100
                                logger.info(f"  [mstarpy] expense for {symbol}: {raw_mstar_expense}% -> {mstar_expense} decimal")
                            else:
                                logger.warning(f"  [mstarpy] NO ongoingCharge field for {symbol}!")
                                logger.info(f"  [mstarpy] Available fields: {list(fields.keys())}")
                            
                            mstar_data = {
                                "security_id": meta.get("securityID"),
                                "name": self._get_field_value(fields, "name", "Unknown"),
                                "category": self._get_field_value(fields, "morningstarCategory", ""),
                                "category_id": meta.get("categoryId", ""),
                                "star_rating": int(self._get_field_value(fields, "fundStarRating", 0) or 0),
                                "medalist_rating": self._get_field_value(fields, "medalistRating", "") or "Unknown",
                                "return_m12": self._get_field_value(fields, "totalReturn", 0) or 0,
                                "fund_size": self._get_field_value(fields, "fundSize", 0) or 0,
                                "exchange": exchange,
                                "type": "etf" if inv_type == "FE" else "mutual_fund"
                            }
                            break
                    if mstar_data:
                        break
            except Exception as e:
                logger.warning(f"[mstarpy] Error searching for {symbol}: {e}")
                continue
        
        # Log mstarpy result
        if mstar_data:
            logger.info(f"  [mstarpy] SUCCESS for {symbol}: expense={mstar_expense}")
        else:
            logger.warning(f"  [mstarpy] FAILED for {symbol}: no matching fund found")
        
        # STEP 2: Get yfinance data as fallback (for expense ratio and category)
        yf_expense, yf_category = self._get_expense_ratio_yfinance(symbol)
        
        # STEP 3: Combine data
        # Prefer mstarpy expense ratio (more consistent), fallback to yfinance
        final_expense = mstar_expense if mstar_expense > 0 else yf_expense
        
        # SANITY CHECK: Known low-cost Vanguard/iShares ETFs
        # These should NEVER have expense ratios > 0.5%
        LOW_COST_ETFS = {'VOO', 'VTI', 'VUG', 'VTV', 'VEA', 'VWO', 'BND', 'VXUS',
                        'IVV', 'SPY', 'QQQ', 'IWM', 'IWF', 'IWD', 'AGG', 'LQD'}
        
        if symbol in LOW_COST_ETFS and final_expense > 0.005:  # > 0.5%
            logger.warning(f"  SANITY CHECK FAILED for {symbol}: expense {final_expense} ({final_expense*100:.2f}%) is too high!")
            logger.warning(f"  This is a known low-cost ETF. Expense should be < 0.5%.")
            logger.warning(f"  mstar_expense={mstar_expense}, yf_expense={yf_expense}")
            # If we got a clearly wrong value, try to fix it
            if final_expense > 0.01:  # > 1%, definitely wrong for these ETFs
                # Assume the value was in percentage form and we didn't convert
                final_expense = final_expense / 100
                logger.warning(f"  Corrected expense to: {final_expense} ({final_expense*100:.4f}%)")
        
        logger.info(f"  Final expense ratio for {symbol}: {final_expense} ({final_expense*100:.4f}%) [mstar={mstar_expense}, yf={yf_expense}]")
        
        if mstar_data:
            
            # Use yfinance category if mstar doesn't have one
            category = mstar_data.get('category') or yf_category or 'Unknown'
            
            fund_data = {
                "security_id": mstar_data.get("security_id"),
                "ticker": symbol,
                "name": mstar_data.get("name", symbol),
                "category": category,
                "category_id": mstar_data.get("category_id", ""),
                "expense_ratio": final_expense,
                "star_rating": mstar_data.get("star_rating", 0),
                "medalist_rating": mstar_data.get("medalist_rating", "Unknown"),
                "return_m12": mstar_data.get("return_m12", 0),
                "return_m36": 0,
                "return_m60": 0,
                "fund_size": mstar_data.get("fund_size", 0),
                "exchange": mstar_data.get("exchange", ""),
                "type": mstar_data.get("type", "etf")
            }
        else:
            # No mstarpy data, use yfinance only
            fund_data = {
                "security_id": "",
                "ticker": symbol,
                "name": symbol,
                "category": yf_category or "Unknown",
                "category_id": "",
                "expense_ratio": yf_expense,
                "star_rating": 0,
                "medalist_rating": "Unknown",
                "return_m12": 0,
                "return_m36": 0,
                "return_m60": 0,
                "fund_size": 0,
                "exchange": "",
                "type": "etf"
            }
        
        # Cache the result
        self.cache[cache_key] = {
            'timestamp': datetime.now().timestamp(),
            'data': fund_data
        }
        self._save_cache()
        
        logger.info(f"Found fund: {symbol} - {fund_data['name']} (ER: {fund_data['expense_ratio']:.4f}, Rating: {fund_data['medalist_rating']})")
        return fund_data
    
    def _get_field_value(self, fields: Dict, field_name: str, default=None):
        """Extract value from mstarpy fields structure"""
        field_data = fields.get(field_name, {})
        if isinstance(field_data, dict):
            return field_data.get("value", default)
        return field_data if field_data is not None else default
    
    def _map_analyst_rating(self, rating_scale) -> str:
        """Map analyst rating scale to medalist rating name"""
        rating_map = {
            5: "Gold",
            4: "Silver", 
            3: "Bronze",
            2: "Neutral",
            1: "Negative",
            "5": "Gold",
            "4": "Silver",
            "3": "Bronze",
            "2": "Neutral",
            "1": "Negative"
        }
        return rating_map.get(rating_scale, "Unknown")
    
    def analyze_fund_expenses(self, holdings: List[Dict]) -> List[FundExpenseInfo]:
        """
        Analyze expense ratios for all ETF/Mutual Fund holdings
        
        Args:
            holdings: List of holdings from HoldingsAggregator
            
        Returns:
            List of FundExpenseInfo sorted by expense ratio (descending)
        """
        logger.info("Analyzing fund expenses...")
        
        # Filter to only ETFs and Mutual Funds
        funds = [h for h in holdings if h.get('asset_type') in ['etf', 'mutual_fund']]
        
        if not funds:
            logger.info("No ETFs or Mutual Funds found in holdings")
            return []
        
        logger.info(f"Found {len(funds)} funds to analyze")
        
        expense_info = []
        
        for holding in funds:
            symbol = holding.get('symbol', '')
            total_value = float(holding.get('total_value', 0))
            
            if not symbol or total_value <= 0:
                continue
            
            try:
                fund_data = self._search_fund(symbol)
                
                if fund_data:
                    expense_ratio = fund_data.get('expense_ratio', 0)
                    annual_expense = total_value * expense_ratio
                    
                    info = FundExpenseInfo(
                        symbol=symbol,
                        name=fund_data.get('name', symbol),
                        category=fund_data.get('category', 'Unknown'),
                        category_id=fund_data.get('category_id', ''),
                        expense_ratio=expense_ratio,
                        portfolio_value=total_value,
                        annual_expense=annual_expense,
                        medalist_rating=fund_data.get('medalist_rating', 'Unknown'),
                        star_rating=fund_data.get('star_rating', 0),
                        return_m12=fund_data.get('return_m12', 0),
                        security_id=fund_data.get('security_id', '')
                    )
                    expense_info.append(info)
                    logger.info(f"  {symbol}: ER={expense_ratio:.4f}, Annual=${annual_expense:.2f}")
                else:
                    # Create entry with unknown expense ratio
                    expense_info.append(FundExpenseInfo(
                        symbol=symbol,
                        name=holding.get('name', symbol),
                        category='Unknown',
                        category_id='',
                        expense_ratio=0,
                        portfolio_value=total_value,
                        annual_expense=0,
                        medalist_rating='Unknown',
                        star_rating=0,
                        return_m12=0,
                        security_id=''
                    ))
            
            except Exception as e:
                logger.error(f"Error analyzing fund {symbol}: {e}")
                continue
        
        # Sort by expense ratio (descending) - highest expense first
        expense_info.sort(key=lambda x: x.expense_ratio, reverse=True)
        
        # Return top 10
        return expense_info[:10]
    
    def find_category_peers(
        self, 
        category_id: str, 
        category_name: str,
        exclude_symbols: List[str] = None,
        min_rating: str = "Silver"
    ) -> List[PeerFund]:
        """
        Find top-rated peer funds in a category
        
        Args:
            category_id: Morningstar category ID
            category_name: Category name for display
            exclude_symbols: Symbols to exclude (already owned)
            min_rating: Minimum medalist rating ('Gold' or 'Silver')
            
        Returns:
            List of PeerFund objects
        """
        if not category_name:
            logger.warning(f"No category name provided for peer search")
            return []
        
        exclude_symbols = set(s.upper() for s in (exclude_symbols or []))
        
        logger.info(f"="*50)
        logger.info(f"PEER SEARCH for category: '{category_name}'")
        logger.info(f"  Excluding symbols: {exclude_symbols}")
        logger.info(f"  Min rating: {min_rating}")
        logger.info(f"="*50)
        
        peers = []
        
        # Map category names to better search terms
        # Morningstar categories have specific names
        category_search_map = {
            'Large Blend': ['Large Blend', 'S&P 500', 'Total Stock'],
            'Large Growth': ['Large Growth'],
            'Large Value': ['Large Value'],
            'Mid-Cap Blend': ['Mid-Cap Blend', 'Mid Cap'],
            'Mid-Cap Growth': ['Mid-Cap Growth'],
            'Mid-Cap Value': ['Mid-Cap Value'],
            'Small Blend': ['Small Blend', 'Small Cap'],
            'Small Growth': ['Small Growth'],
            'Small Value': ['Small Value'],
            'Foreign Large Blend': ['Foreign Large', 'International'],
            'Diversified Emerging Mkts': ['Emerging Markets'],
            'Technology': ['Technology'],
        }
        
        # Get search terms for this category
        search_terms = category_search_map.get(category_name, [category_name])
        
        # Also add the original category name and individual words
        if category_name not in search_terms:
            search_terms.insert(0, category_name)
        
        logger.info(f"  Search terms to try: {search_terms}")
        
        try:
            for search_term in search_terms:
                if len(peers) >= 10:
                    break
                    
                for inv_type in ["FE", "FO"]:
                    try:
                        logger.info(f"  Searching: term='{search_term}', type={inv_type}")
                        
                        results = ms.screener_universe(
                            search_term,
                            language="en-gb",
                            field=[
                                "name", "ticker", "exchange", "morningstarCategory",
                                "ongoingCharge", "fundStarRating", "medalistRating",
                                "totalReturn", "fundSize"
                            ],
                            filters={"investmentType": inv_type},
                            pageSize=50
                        )
                        
                        logger.info(f"    Got {len(results) if results else 0} results")
                        
                        if results:
                            for result in results:
                                meta = result.get("meta", {})
                                fields = result.get("fields", {})
                                
                                ticker = (meta.get("ticker", "") or "").upper()
                                exchange = meta.get("exchange", "") or ""
                                fund_category = self._get_field_value(fields, "morningstarCategory", "")
                                medalist = self._get_field_value(fields, "medalistRating", "")
                                name = self._get_field_value(fields, "name", "")
                                
                                # Only US exchanges
                                if exchange not in ["ARCX", "XNAS", "XNYS", "BATS", "NYSE", "NASDAQ"]:
                                    continue
                                    
                                # Skip already-owned funds
                                if ticker in exclude_symbols:
                                    logger.debug(f"    Skipping {ticker} - already owned")
                                    continue
                                
                                # Skip if no ticker
                                if not ticker:
                                    continue
                                
                                # Check if already added
                                if any(p.ticker == ticker for p in peers):
                                    continue
                                
                                # Log what we found for debugging
                                logger.debug(f"    Found: {ticker} ({name[:30]}...) - Category: {fund_category}, Rating: {medalist}")
                                
                                # Filter by medalist rating
                                if min_rating == "Gold" and medalist != "Gold":
                                    continue
                                if min_rating == "Silver" and medalist not in ["Gold", "Silver"]:
                                    logger.debug(f"    Skipping {ticker} - rating {medalist} doesn't meet {min_rating}")
                                    continue
                                
                                # Category matching - be more flexible
                                if category_name and fund_category:
                                    cat_lower = category_name.lower()
                                    fund_cat_lower = fund_category.lower()
                                    
                                    # Direct match
                                    if cat_lower == fund_cat_lower:
                                        pass  # Perfect match
                                    # Check for overlap in category words
                                    else:
                                        cat_words = set(cat_lower.replace('-', ' ').split())
                                        fund_words = set(fund_cat_lower.replace('-', ' ').split())
                                        common_words = cat_words.intersection(fund_words)
                                        
                                        # Need at least one meaningful word match
                                        meaningful_common = common_words - {'cap', 'fund', 'index', 'the', 'a'}
                                        if not meaningful_common:
                                            logger.debug(f"    Skipping {ticker} - category mismatch: '{fund_category}' vs '{category_name}'")
                                            continue
                                
                                # Get expense ratio
                                expense_ratio_pct = self._get_field_value(fields, "ongoingCharge", 0)
                                expense_ratio = (expense_ratio_pct / 100) if expense_ratio_pct else 0
                                
                                # If no expense ratio from mstarpy, try yfinance
                                if expense_ratio == 0:
                                    expense_ratio, _ = self._get_expense_ratio_yfinance(ticker)
                                
                                peer = PeerFund(
                                    security_id=meta.get("securityID", ""),
                                    name=name or "Unknown",
                                    ticker=ticker,
                                    expense_ratio=expense_ratio,
                                    medalist_rating=medalist or "Unknown",
                                    star_rating=int(self._get_field_value(fields, "fundStarRating", 0) or 0),
                                    return_m12=self._get_field_value(fields, "totalReturn", 0) or 0,
                                    return_m36=0,
                                    return_m60=0,
                                    fund_size=self._get_field_value(fields, "fundSize", 0) or 0
                                )
                                peers.append(peer)
                                logger.info(f"    ✓ Added peer: {ticker} ({medalist}, ER: {expense_ratio*100:.2f}%)")
                                
                    except Exception as e:
                        logger.warning(f"    Error in peer search for '{search_term}': {e}")
                        continue
        
        except Exception as e:
            logger.error(f"Error searching for peers: {e}")
            import traceback
            traceback.print_exc()
        
        # Sort by medalist rating (Gold first), then by expense ratio (low first)
        rating_order = {"Gold": 0, "Silver": 1, "Bronze": 2, "Neutral": 3, "Negative": 4, "Unknown": 5}
        peers.sort(key=lambda x: (rating_order.get(x.medalist_rating, 5), x.expense_ratio))
        
        logger.info(f"  FINAL: Found {len(peers)} peer funds for category '{category_name}'")
        for p in peers[:5]:
            logger.info(f"    - {p.ticker}: {p.medalist_rating}, ER={p.expense_ratio*100:.2f}%")
        
        return peers[:10]
    
    def get_fund_nav_history(
        self, 
        security_id: str, 
        days: int = 365,
        symbol: str = None
    ) -> Optional[pd.DataFrame]:
        """
        Get historical NAV data for a fund
        
        Args:
            security_id: Morningstar security ID
            days: Number of days of history
            symbol: Ticker symbol (for yfinance fallback)
            
        Returns:
            DataFrame with date, nav, totalReturn columns
        """
        import time
        
        # Try mstarpy first if we have security_id
        if security_id:
            try:
                logger.info(f"[NAV] Fetching from mstarpy: {security_id} (symbol={symbol})")
                start_time = time.time()
                
                fund = ms.Funds(security_id)
                
                end_date = datetime.now()
                start_date = end_date - timedelta(days=days)
                
                history = fund.nav(
                    start_date=start_date,
                    end_date=end_date,
                    frequency="daily"
                )
                
                elapsed = time.time() - start_time
                
                if history:
                    df = pd.DataFrame(history)
                    logger.info(f"[NAV] mstarpy SUCCESS for {security_id}: {len(df)} records in {elapsed:.1f}s")
                    return df
                else:
                    logger.warning(f"[NAV] mstarpy returned empty for {security_id} in {elapsed:.1f}s")
                
            except Exception as e:
                elapsed = time.time() - start_time if 'start_time' in dir() else 0
                error_msg = str(e)
                # Check for 401 errors
                if '401' in error_msg or 'Unauthorized' in error_msg:
                    logger.warning(f"[NAV] mstarpy 401 AUTH ERROR for {security_id} in {elapsed:.1f}s - falling back to yfinance")
                else:
                    logger.warning(f"[NAV] mstarpy FAILED for {security_id} in {elapsed:.1f}s: {error_msg[:100]}")
        
        # Fallback to yfinance if we have symbol
        if symbol:
            try:
                logger.info(f"[NAV] Fetching from yfinance: {symbol}")
                start_time = time.time()
                
                ticker = yf.Ticker(symbol)
                
                end_date = datetime.now()
                start_date = end_date - timedelta(days=days)
                
                hist = ticker.history(start=start_date, end=end_date, interval="1d")
                
                elapsed = time.time() - start_time
                
                if hist is not None and not hist.empty:
                    # Convert to NAV-like format
                    df = pd.DataFrame({
                        'date': hist.index.strftime('%Y-%m-%d'),
                        'nav': hist['Close'].values,
                        'totalReturn': hist['Close'].values  # Use close price as proxy
                    })
                    logger.info(f"[NAV] yfinance SUCCESS for {symbol}: {len(df)} records in {elapsed:.1f}s")
                    return df
                else:
                    logger.warning(f"[NAV] yfinance returned empty for {symbol} in {elapsed:.1f}s")
                    
            except Exception as e:
                elapsed = time.time() - start_time if 'start_time' in dir() else 0
                logger.warning(f"[NAV] yfinance FAILED for {symbol} in {elapsed:.1f}s: {str(e)[:100]}")
        
        logger.error(f"[NAV] ALL METHODS FAILED for security_id={security_id}, symbol={symbol}")
        return None
    
    def compare_fund_performance(
        self,
        fund_info: FundExpenseInfo,
        peers: List[PeerFund],
        days: int = 365
    ) -> Dict:
        """
        Compare fund performance against peers
        
        Returns dict with:
        - fund_nav: DataFrame of fund NAV history
        - peer_navs: Dict of peer security_id -> DataFrame
        - comparison: Summary comparison data
        """
        import math
        
        def safe_float(val, default=0):
            """Convert to float, handling NaN and None"""
            if val is None:
                return default
            try:
                f = float(val)
                if math.isnan(f) or math.isinf(f):
                    return default
                return f
            except (ValueError, TypeError):
                return default
        
        result = {
            'fund_nav': None,
            'peer_navs': {},
            'comparison': {
                'fund': {
                    'symbol': fund_info.symbol,
                    'name': fund_info.name,
                    'return_m12': safe_float(fund_info.return_m12),
                    'expense_ratio': safe_float(fund_info.expense_ratio)
                },
                'peers': []
            }
        }
        
        # Get fund NAV
        if fund_info.security_id:
            result['fund_nav'] = self.get_fund_nav_history(fund_info.security_id, days)
        
        # Get peer NAVs (limit to top 3 for performance)
        for peer in peers[:3]:
            if peer.security_id:
                nav_df = self.get_fund_nav_history(peer.security_id, days)
                if nav_df is not None:
                    result['peer_navs'][peer.security_id] = nav_df
                
                result['comparison']['peers'].append({
                    'symbol': peer.ticker,
                    'name': peer.name,
                    'return_m12': safe_float(peer.return_m12),
                    'expense_ratio': safe_float(peer.expense_ratio),
                    'medalist_rating': peer.medalist_rating
                })
        
        return result
    
    def get_expense_analysis_summary(self, holdings: List[Dict]) -> Dict:
        """
        Get complete expense analysis for dashboard display
        
        Returns:
            Dict with:
            - top_funds: List of top 10 funds by expense ratio
            - total_annual_expenses: Total annual expense across all funds
            - peer_recommendations: Dict of category -> recommended peers
            - charts_data: Data for expense/performance charts
        """
        # Analyze expenses
        top_funds = self.analyze_fund_expenses(holdings)
        
        total_expenses = sum(f.annual_expense for f in top_funds)
        total_value = sum(f.portfolio_value for f in top_funds)
        
        # Get peer recommendations for each unique category
        peer_recommendations = {}
        seen_categories = set()
        owned_symbols = [f.symbol for f in top_funds]
        
        for fund in top_funds:
            # Use category name for peer search (category_id is optional)
            if fund.category and fund.category != 'Unknown' and fund.category not in seen_categories:
                seen_categories.add(fund.category)
                peers = self.find_category_peers(
                    fund.category_id,  # May be empty, that's OK
                    fund.category,
                    exclude_symbols=owned_symbols
                )
                if peers:
                    peer_recommendations[fund.category] = [
                        {
                            'symbol': p.ticker,
                            'name': p.name,
                            'expense_ratio': p.expense_ratio,
                            'medalist_rating': p.medalist_rating,
                            'star_rating': p.star_rating,
                            'return_m12': p.return_m12
                        }
                        for p in peers[:5]  # Top 5 per category
                    ]
        
        return {
            'top_funds': [
                {
                    'symbol': f.symbol,
                    'name': f.name,
                    'category': f.category,
                    'expense_ratio': f.expense_ratio,
                    'expense_ratio_pct': f.expense_ratio * 100,
                    'portfolio_value': f.portfolio_value,
                    'annual_expense': f.annual_expense,
                    'medalist_rating': f.medalist_rating,
                    'star_rating': f.star_rating,
                    'return_m12': f.return_m12,
                    'security_id': f.security_id
                }
                for f in top_funds
            ],
            'total_annual_expenses': total_expenses,
            'total_fund_value': total_value,
            'weighted_expense_ratio': (total_expenses / total_value * 100) if total_value > 0 else 0,
            'peer_recommendations': peer_recommendations,
            'categories_analyzed': list(seen_categories)
        }