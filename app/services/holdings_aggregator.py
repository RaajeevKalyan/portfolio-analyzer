"""
Holdings Aggregator Service - WITH SECTOR/COUNTRY

CRITICAL FIX: Pass sector and country from database to UI
"""
import logging
from typing import List, Dict, Optional
from decimal import Decimal
from collections import defaultdict
from app.database import db_session
from app.models import BrokerAccount, PortfolioSnapshot, Holding

logger = logging.getLogger(__name__)


class HoldingsAggregator:
    """Aggregate and analyze portfolio holdings"""
    
    def get_aggregated_holdings(self) -> Dict:
        """Get current holdings aggregated across all brokers"""
        with db_session() as session:
            latest_snapshots = self._get_latest_snapshots(session)
            
            if not latest_snapshots:
                return {
                    'total_value': Decimal('0.00'),
                    'holdings': [],
                    'direct_holdings': {},
                    'underlying_holdings': {}
                }
            
            aggregated = self._aggregate_by_symbol(session, latest_snapshots)
            total_value = sum(h['total_value'] for h in aggregated)
            direct_holdings = self._get_direct_holdings(aggregated)
            underlying_holdings = self._get_underlying_holdings(session, aggregated)
            overlaps = self._detect_overlaps(direct_holdings, underlying_holdings)
            
            for holding in aggregated:
                symbol = holding['symbol']
                if symbol in overlaps:
                    holding['has_overlap'] = True
                    holding['overlap_sources'] = overlaps[symbol]
                else:
                    holding['has_overlap'] = False
                    holding['overlap_sources'] = []
            
            return {
                'total_value': total_value,
                'holdings': aggregated,
                'direct_holdings': direct_holdings,
                'underlying_holdings': underlying_holdings,
                'overlaps': overlaps
            }
    
    def _get_latest_snapshots(self, session) -> List[PortfolioSnapshot]:
        """Get the most recent snapshot for each active broker"""
        from sqlalchemy import desc
        
        latest_snapshots = []
        accounts = session.query(BrokerAccount).filter_by(is_active=True).all()
        
        for account in accounts:
            snapshot = session.query(PortfolioSnapshot).filter_by(
                broker_account_id=account.id
            ).order_by(desc(PortfolioSnapshot.snapshot_date)).first()
            
            if snapshot:
                latest_snapshots.append(snapshot)
        
        return latest_snapshots
    
    def _aggregate_by_symbol(self, session, snapshots: List[PortfolioSnapshot]) -> List[Dict]:
        """Aggregate holdings by symbol across all snapshots"""
        symbol_data = defaultdict(lambda: {
            'symbol': '',
            'name': '',
            'total_quantity': Decimal('0.00'),
            'average_price': Decimal('0.00'),
            'total_value': Decimal('0.00'),
            'asset_type': '',
            'brokers': [],
            'is_etf_or_mf': False,
            'underlying_count': 0,
            'sector': None,          # NEW
            'country': None          # NEW
        })
        
        for snapshot in snapshots:
            broker_name = snapshot.broker_account.broker_name
            
            for holding in snapshot.holdings:
                symbol = holding.symbol
                data = symbol_data[symbol]
                
                if not data['symbol']:
                    data['symbol'] = holding.symbol
                    data['name'] = holding.name
                    data['asset_type'] = holding.asset_type
                    data['is_etf_or_mf'] = holding.asset_type in ['etf', 'mutual_fund']
                    
                    # NEW: Add sector and country
                    data['sector'] = holding.sector
                    data['country'] = holding.country
                    
                    if holding.underlying_holdings_list:
                        data['underlying_count'] = len(holding.underlying_holdings_list)
                
                data['total_quantity'] += holding.quantity
                data['total_value'] += holding.total_value
                
                data['brokers'].append({
                    'broker': broker_name,
                    'broker_display': broker_name.replace('_', ' ').title(),
                    'quantity': holding.quantity,
                    'price': holding.price,
                    'value': holding.total_value,
                    'account_last4': snapshot.broker_account.account_number_last4
                })
        
        result = []
        total_portfolio_value = sum(data['total_value'] for data in symbol_data.values())
        
        for data in symbol_data.values():
            if data['total_quantity'] > 0:
                data['average_price'] = data['total_value'] / data['total_quantity']
            
            if total_portfolio_value > 0:
                data['allocation_pct'] = float(data['total_value'] / total_portfolio_value)
            else:
                data['allocation_pct'] = 0.0
            
            result.append(data)
        
        result.sort(key=lambda x: x['total_value'], reverse=True)
        
        return result
    
    def _get_direct_holdings(self, aggregated: List[Dict]) -> Dict[str, Dict]:
        """Extract direct stock holdings"""
        direct = {}
        
        for holding in aggregated:
            symbol = holding['symbol']
            direct[symbol] = {
                'value': holding['total_value'],
                'allocation': holding['allocation_pct'],
                'quantity': holding['total_quantity']
            }
        
        return direct
    
    def _get_underlying_holdings(self, session, aggregated: List[Dict]) -> Dict[str, Dict]:
        """Extract and aggregate underlying holdings from all ETFs/MFs"""
        underlying_total = defaultdict(lambda: {
            'symbol': '',
            'name': '',
            'total_value': Decimal('0.00'),
            'sources': []
        })
        
        for holding in aggregated:
            if not holding['is_etf_or_mf']:
                continue
            
            parent_symbol = holding['symbol']
            parent_value = holding['total_value']
            
            snapshot_ids = []
            for broker_info in holding['brokers']:
                broker_account = session.query(BrokerAccount).filter_by(
                    broker_name=broker_info['broker']
                ).first()
                
                if broker_account:
                    from sqlalchemy import desc
                    snapshot = session.query(PortfolioSnapshot).filter_by(
                        broker_account_id=broker_account.id
                    ).order_by(desc(PortfolioSnapshot.snapshot_date)).first()
                    
                    if snapshot:
                        snapshot_ids.append(snapshot.id)
            
            holdings_objs = session.query(Holding).filter(
                Holding.portfolio_snapshot_id.in_(snapshot_ids),
                Holding.symbol == parent_symbol
            ).all()
            
            for holding_obj in holdings_objs:
                underlying_list = holding_obj.underlying_holdings_list
                
                if not underlying_list:
                    continue
                
                for underlying in underlying_list:
                    symbol = underlying['symbol']
                    name = underlying.get('name', symbol)
                    value = Decimal(str(underlying.get('value', 0)))
                    weight = underlying.get('weight', 0)
                    
                    data = underlying_total[symbol]
                    
                    if not data['symbol']:
                        data['symbol'] = symbol
                        data['name'] = name
                    
                    data['total_value'] += value
                    data['sources'].append({
                        'fund': parent_symbol,
                        'weight': weight,
                        'value': value
                    })
        
        result = {}
        for symbol, data in underlying_total.items():
            result[symbol] = data
        
        return result
    
    def _detect_overlaps(self, direct: Dict, underlying: Dict) -> Dict[str, List[Dict]]:
        """Detect stocks held both directly and through ETFs/MFs"""
        overlaps = {}
        
        for symbol in direct.keys():
            if symbol in underlying:
                overlaps[symbol] = {
                    'direct_value': direct[symbol]['value'],
                    'underlying_value': underlying[symbol]['total_value'],
                    'underlying_sources': underlying[symbol]['sources']
                }
        
        return overlaps


def get_current_holdings() -> Dict:
    """Convenience function to get current aggregated holdings"""
    aggregator = HoldingsAggregator()
    return aggregator.get_aggregated_holdings()