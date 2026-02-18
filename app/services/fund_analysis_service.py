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
            Tuple of (expense_ratio as decimal, category name)
        """
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info or {}
            category = info.get('category', '')
            
            # Method 1: Try funds_data (newer yfinance API)
            try:
                funds_data = ticker.funds_data
                if funds_data:
                    # Get expense ratio from fund_operations
                    try:
                        fund_ops = funds_data.fund_operations
                        if fund_ops is not None and hasattr(fund_ops, 'empty') and not fund_ops.empty:
                            # Try various expense ratio field names
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
                                    # Handle both Series and scalar values
                                    if hasattr(val, 'iloc'):
                                        val = val.iloc[0] if len(val) > 0 else None
                                    elif hasattr(val, 'values'):
                                        val = val.values[0] if len(val.values) > 0 else None
                                    
                                    if val is not None and pd.notna(val):
                                        expense = float(val)
                                        # Normalize: if > 1, it's likely percentage (e.g., 0.75 means 0.75%)
                                        if expense > 1:
                                            expense = expense / 100
                                        logger.info(f"  yfinance fund_ops expense for {symbol}: {expense}")
                                        return expense, category
                        
                        # Try as dict if DataFrame doesn't work
                        if isinstance(fund_ops, dict):
                            for field in ['annualReportExpenseRatio', 'totalExpenseRatio', 'netExpenseRatio']:
                                if field in fund_ops and fund_ops[field]:
                                    expense = float(fund_ops[field])
                                    if expense > 1:
                                        expense = expense / 100
                                    return expense, category
                                    
                    except Exception as e:
                        logger.debug(f"  fund_operations parsing error for {symbol}: {e}")
                    
                    # Try fund_overview
                    try:
                        overview = funds_data.fund_overview
                        if overview and isinstance(overview, dict):
                            for field in ['expenseRatio', 'netExpenseRatio', 'annualReportExpenseRatio']:
                                if field in overview and overview[field]:
                                    expense = float(overview[field])
                                    if expense > 1:
                                        expense = expense / 100
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
                'annualHoldingsTurnover'  # Sometimes this is reported instead
            ]
            
            for field in expense_info_fields:
                if field in info and info[field] is not None:
                    expense = float(info[field])
                    # yfinance returns as decimal (0.0075 for 0.75%)
                    # But sometimes as percentage (0.75 for 0.75%)
                    if expense > 0.1:  # Likely percentage format
                        expense = expense / 100
                    if expense > 0:
                        logger.info(f"  yfinance info expense for {symbol}: {expense}")
                        return expense, category
            
            return 0, category
                
        except Exception as e:
            logger.warning(f"Error getting yfinance data for {symbol}: {e}")
        
        return 0, ''
    
    def _search_fund(self, symbol: str) -> Optional[Dict]:
        """
        Search for a fund by symbol and get its details
        Returns fund info including category, expense ratio, etc.
        
        Uses yfinance for expense ratio (more reliable) and mstarpy for ratings.
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
        
        # STEP 1: Get expense ratio from yfinance (more reliable)
        expense_ratio, yf_category = self._get_expense_ratio_yfinance(symbol)
        
        # STEP 2: Get ratings and additional info from mstarpy
        us_exchanges = ["ARCX", "XNAS", "XNYS", "BATS", "NYSE", "NASDAQ"]
        mstar_data = None
        
        for inv_type in ["FE", "FO"]:  # ETF, Mutual Fund
            try:
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
                
                if results:
                    for result in results:
                        meta = result.get("meta", {})
                        fields = result.get("fields", {})
                        
                        ticker = meta.get("ticker", "") or ""
                        exchange = meta.get("exchange", "") or ""
                        
                        if ticker.upper() == symbol and exchange in us_exchanges:
                            # Get mstarpy expense ratio as fallback
                            mstar_expense = self._get_field_value(fields, "ongoingCharge", 0)
                            if mstar_expense:
                                mstar_expense = mstar_expense / 100  # Convert to decimal
                            
                            mstar_data = {
                                "security_id": meta.get("securityID"),
                                "name": self._get_field_value(fields, "name", "Unknown"),
                                "category": self._get_field_value(fields, "morningstarCategory", ""),
                                "category_id": meta.get("categoryId", ""),
                                "mstar_expense_ratio": mstar_expense,
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
                logger.warning(f"Error searching mstarpy for {symbol}: {e}")
                continue
        
        # STEP 3: Combine data, preferring yfinance expense ratio
        if mstar_data:
            # Use yfinance expense ratio if available, otherwise mstarpy
            final_expense = expense_ratio if expense_ratio > 0 else mstar_data.get('mstar_expense_ratio', 0)
            
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
                "expense_ratio": expense_ratio,
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
        
        logger.info(f"Searching for peers in category: {category_name}")
        
        peers = []
        
        try:
            # Search for funds using category keywords
            # Extract key words from category (e.g., "Large Growth" -> search for "Large Growth")
            search_terms = [category_name]
            
            # Also try individual words for broader search
            words = category_name.split()
            if len(words) > 1:
                search_terms.append(words[-1])  # e.g., "Growth" from "Large Growth"
            
            for search_term in search_terms:
                for inv_type in ["FE", "FO"]:
                    try:
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
                        
                        if results:
                            for result in results:
                                meta = result.get("meta", {})
                                fields = result.get("fields", {})
                                
                                ticker = (meta.get("ticker", "") or "").upper()
                                exchange = meta.get("exchange", "") or ""
                                fund_category = self._get_field_value(fields, "morningstarCategory", "")
                                medalist = self._get_field_value(fields, "medalistRating", "")
                                
                                # Only US exchanges
                                if exchange not in ["ARCX", "XNAS", "XNYS", "BATS", "NYSE", "NASDAQ"]:
                                    continue
                                    
                                # Skip already-owned funds
                                if ticker in exclude_symbols:
                                    continue
                                
                                # Skip if no ticker
                                if not ticker:
                                    continue
                                
                                # Check if already added
                                if any(p.ticker == ticker for p in peers):
                                    continue
                                
                                # Filter by medalist rating
                                if min_rating == "Gold" and medalist != "Gold":
                                    continue
                                if min_rating == "Silver" and medalist not in ["Gold", "Silver"]:
                                    continue
                                
                                # Category must somewhat match
                                if category_name and fund_category:
                                    cat_lower = category_name.lower()
                                    fund_cat_lower = fund_category.lower()
                                    # Check for overlap in category words
                                    cat_words = set(cat_lower.split())
                                    fund_words = set(fund_cat_lower.split())
                                    if not cat_words.intersection(fund_words):
                                        continue
                                
                                # Get expense ratio from mstarpy
                                expense_ratio_pct = self._get_field_value(fields, "ongoingCharge", 0)
                                expense_ratio = (expense_ratio_pct / 100) if expense_ratio_pct else 0
                                
                                # If no expense ratio from mstarpy, try yfinance
                                if expense_ratio == 0:
                                    expense_ratio, _ = self._get_expense_ratio_yfinance(ticker)
                                
                                peer = PeerFund(
                                    security_id=meta.get("securityID", ""),
                                    name=self._get_field_value(fields, "name", "Unknown"),
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
                                
                    except Exception as e:
                        logger.warning(f"Error in peer search for {search_term}: {e}")
                        continue
                
                # If we found enough peers, stop searching
                if len(peers) >= 10:
                    break
        
        except Exception as e:
            logger.error(f"Error searching for peers: {e}")
            import traceback
            traceback.print_exc()
        
        # Sort by medalist rating (Gold first), then by expense ratio (low first)
        rating_order = {"Gold": 0, "Silver": 1, "Bronze": 2, "Neutral": 3, "Negative": 4, "Unknown": 5}
        peers.sort(key=lambda x: (rating_order.get(x.medalist_rating, 5), x.expense_ratio))
        
        logger.info(f"Found {len(peers)} peer funds for category '{category_name}'")
        return peers[:10]
    
    def get_fund_nav_history(
        self, 
        security_id: str, 
        days: int = 365
    ) -> Optional[pd.DataFrame]:
        """
        Get historical NAV data for a fund
        
        Args:
            security_id: Morningstar security ID
            days: Number of days of history
            
        Returns:
            DataFrame with date, nav, totalReturn columns
        """
        if not security_id:
            return None
        
        try:
            fund = ms.Funds(security_id)
            
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)
            
            history = fund.nav(
                start_date=start_date,
                end_date=end_date,
                frequency="daily"
            )
            
            if history:
                df = pd.DataFrame(history)
                logger.info(f"Got {len(df)} NAV records for {security_id}")
                return df
            
        except Exception as e:
            logger.error(f"Error getting NAV history for {security_id}: {e}")
        
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
        result = {
            'fund_nav': None,
            'peer_navs': {},
            'comparison': {
                'fund': {
                    'symbol': fund_info.symbol,
                    'name': fund_info.name,
                    'return_m12': fund_info.return_m12,
                    'expense_ratio': fund_info.expense_ratio
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
                    'return_m12': peer.return_m12,
                    'expense_ratio': peer.expense_ratio,
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