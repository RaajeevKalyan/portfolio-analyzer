"""
Asset Type Resolver - Shared utility for determining security types

Used by CSV parsers and cache generation to consistently classify securities
as stock, etf, mutual_fund, bond, etc.

Priority:
1. Check stock_info_cache for previously resolved asset_type
2. Fetch from yfinance quoteType (authoritative source)
3. Fall back to heuristics (symbol patterns, description keywords)
"""
import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


class AssetTypeResolver:
    """Resolves asset types for securities using cache and yfinance"""
    
    # Common ETF symbols that we know for certain
    KNOWN_ETFS = {
        'VOO', 'VTI', 'SPY', 'QQQ', 'IVV', 'VEA', 'VWO', 'BND', 'AGG',
        'VNQ', 'VGT', 'XLF', 'XLE', 'XLK', 'XLV', 'GLD', 'SLV', 'ARKK',
        'VT', 'VXUS', 'SCHB', 'SCHX', 'ITOT', 'IEMG', 'VIG', 'VYM',
        'SCHD', 'VUG', 'VTV', 'IJR', 'IJH', 'IWM', 'IWF', 'IWD',
        'EFA', 'EEM', 'TLT', 'LQD', 'HYG', 'TIP', 'SHY', 'IEF'
    }
    
    def __init__(self):
        self._stock_info_service = None
        self._yf = None
    
    @property
    def stock_info_service(self):
        """Lazy load stock info service"""
        if self._stock_info_service is None:
            try:
                from app.services.stock_info_service import StockInfoService
                self._stock_info_service = StockInfoService()
            except Exception as e:
                logger.warning(f"Could not load StockInfoService: {e}")
        return self._stock_info_service
    
    @property
    def yf(self):
        """Lazy load yfinance"""
        if self._yf is None:
            try:
                import yfinance as yf
                self._yf = yf
            except ImportError:
                logger.warning("yfinance not available")
        return self._yf
    
    def resolve(
        self, 
        symbol: str, 
        description: str = '', 
        csv_type_field: str = '',
        use_cache: bool = True,
        use_yfinance: bool = True
    ) -> Tuple[str, str]:
        """
        Resolve the asset type for a security.
        
        Args:
            symbol: Ticker symbol
            description: Security description (from CSV)
            csv_type_field: Type field from CSV (e.g., "Stock", "ETF", "Mutual Fund")
            use_cache: Whether to check stock_info_cache
            use_yfinance: Whether to fetch from yfinance if not cached
            
        Returns:
            Tuple of (asset_type, source) where source indicates how it was determined
        """
        symbol_upper = symbol.upper().strip() if symbol else ''
        desc_lower = description.lower() if description else ''
        type_lower = csv_type_field.lower().strip() if csv_type_field else ''
        
        if not symbol_upper:
            return 'unknown', 'no_symbol'
        
        logger.debug(f"Resolving asset type for {symbol_upper}")
        
        # STEP 1: Check cache
        if use_cache and self.stock_info_service:
            cached_info = self.stock_info_service.cache.get(symbol_upper, {})
            if cached_info and cached_info.get('asset_type'):
                asset_type = cached_info['asset_type']
                logger.debug(f"  {symbol_upper} -> {asset_type} (cache)")
                return asset_type, 'cache'
        
        # STEP 2: Fetch from yfinance
        if use_yfinance and self.yf:
            try:
                ticker = self.yf.Ticker(symbol_upper)
                info = ticker.info
                
                if info and info.get('quoteType'):
                    quote_type = info['quoteType']
                    logger.debug(f"  {symbol_upper} yfinance quoteType: {quote_type}")
                    
                    if quote_type == 'ETF':
                        logger.info(f"  {symbol_upper} -> etf (yfinance)")
                        return 'etf', 'yfinance'
                    elif quote_type == 'MUTUALFUND':
                        logger.info(f"  {symbol_upper} -> mutual_fund (yfinance)")
                        return 'mutual_fund', 'yfinance'
                    elif quote_type == 'EQUITY':
                        logger.debug(f"  {symbol_upper} -> stock (yfinance)")
                        return 'stock', 'yfinance'
                    elif quote_type == 'BOND':
                        logger.debug(f"  {symbol_upper} -> bond (yfinance)")
                        return 'bond', 'yfinance'
                    elif quote_type == 'OPTION':
                        logger.debug(f"  {symbol_upper} -> option (yfinance)")
                        return 'option', 'yfinance'
            except Exception as e:
                logger.debug(f"  {symbol_upper} yfinance lookup failed: {e}")
        
        # STEP 3: Check CSV type field
        if type_lower == 'stock' or type_lower == 'equity':
            logger.debug(f"  {symbol_upper} -> stock (csv_type)")
            return 'stock', 'csv_type'
        if type_lower == 'etf':
            logger.debug(f"  {symbol_upper} -> etf (csv_type)")
            return 'etf', 'csv_type'
        if type_lower == 'mutual fund' or type_lower == 'mf':
            logger.debug(f"  {symbol_upper} -> mutual_fund (csv_type)")
            return 'mutual_fund', 'csv_type'
        if type_lower in ('bond', 'bonds', 'fixed income'):
            logger.debug(f"  {symbol_upper} -> bond (csv_type)")
            return 'bond', 'csv_type'
        if type_lower == 'option':
            logger.debug(f"  {symbol_upper} -> option (csv_type)")
            return 'option', 'csv_type'
        
        # STEP 4: Check known ETF list
        if symbol_upper in self.KNOWN_ETFS:
            logger.debug(f"  {symbol_upper} -> etf (known_list)")
            return 'etf', 'known_list'
        
        # STEP 5: Check description keywords
        if 'etf' in desc_lower or 'exchange traded' in desc_lower:
            logger.debug(f"  {symbol_upper} -> etf (description)")
            return 'etf', 'description'
        if 'fund' in desc_lower and 'exchange' not in desc_lower:
            logger.debug(f"  {symbol_upper} -> mutual_fund (description)")
            return 'mutual_fund', 'description'
        if 'index' in desc_lower and 'fund' in desc_lower:
            logger.debug(f"  {symbol_upper} -> mutual_fund (description)")
            return 'mutual_fund', 'description'
        if 'bond' in desc_lower or 'treasury' in desc_lower:
            logger.debug(f"  {symbol_upper} -> bond (description)")
            return 'bond', 'description'
        
        # STEP 6: Symbol pattern heuristics
        # 5-letter symbols ending in X are typically mutual funds
        if len(symbol_upper) == 5 and symbol_upper.endswith('X'):
            logger.debug(f"  {symbol_upper} -> mutual_fund (pattern: 5-letter ending in X)")
            return 'mutual_fund', 'pattern'
        
        # 1-4 letter alphabetic symbols are typically stocks
        if len(symbol_upper) <= 4 and symbol_upper.isalpha():
            logger.debug(f"  {symbol_upper} -> stock (pattern: short alpha)")
            return 'stock', 'pattern'
        
        # Default to stock
        logger.debug(f"  {symbol_upper} -> stock (default)")
        return 'stock', 'default'


# Singleton instance for convenience
_resolver_instance = None

def get_resolver() -> AssetTypeResolver:
    """Get singleton resolver instance"""
    global _resolver_instance
    if _resolver_instance is None:
        _resolver_instance = AssetTypeResolver()
    return _resolver_instance


def resolve_asset_type(
    symbol: str,
    description: str = '',
    csv_type_field: str = '',
    use_cache: bool = True,
    use_yfinance: bool = True
) -> str:
    """
    Convenience function to resolve asset type.
    
    Returns just the asset_type string (not the source).
    """
    resolver = get_resolver()
    asset_type, _ = resolver.resolve(
        symbol, description, csv_type_field, 
        use_cache=use_cache, use_yfinance=use_yfinance
    )
    return asset_type