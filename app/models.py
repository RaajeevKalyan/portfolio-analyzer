"""
Database Models
"""
from sqlalchemy import (
    Column, Integer, String, DateTime, Boolean, Numeric, 
    ForeignKey, Text, Table, UniqueConstraint, Index
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
import json


# Association table for AggregateSnapshot and PortfolioSnapshot (many-to-many)
aggregate_portfolio_association = Table(
    'aggregate_portfolio_association',
    Base.metadata,
    Column('aggregate_snapshot_id', Integer, ForeignKey('aggregate_snapshots.id', ondelete='CASCADE')),
    Column('portfolio_snapshot_id', Integer, ForeignKey('portfolio_snapshots.id', ondelete='CASCADE'))
)


class UserSettings(Base):
    """User preferences and settings"""
    __tablename__ = 'user_settings'
    
    id = Column(Integer, primary_key=True)
    snapshot_retention_limit = Column(Integer, default=25, nullable=False)
    theme_preference = Column(String(10), default='light', nullable=False)  # 'light' or 'dark'
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
    
    def __repr__(self):
        return f"<UserSettings(retention={self.snapshot_retention_limit}, theme={self.theme_preference})>"


class BrokerAccount(Base):
    """Broker account information"""
    __tablename__ = 'broker_accounts'
    
    id = Column(Integer, primary_key=True)
    broker_name = Column(String(50), nullable=False)  # 'merrill', 'fidelity', 'webull', 'robinhood', 'schwab'
    account_number_last4 = Column(String(4), nullable=True)  # Last 4 digits of account number
    account_nickname = Column(String(100), nullable=True)  # User-defined nickname
    last_uploaded_at = Column(DateTime, nullable=True)
    last_csv_filename = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
    
    # Relationships
    portfolio_snapshots = relationship('PortfolioSnapshot', back_populates='broker_account', cascade='all, delete-orphan')
    
    # Constraints
    __table_args__ = (
        Index('idx_broker_name', 'broker_name'),
        UniqueConstraint('broker_name', 'account_number_last4', name='uq_broker_account'),
    )
    
    def __repr__(self):
        return f"<BrokerAccount(broker={self.broker_name}, account=***{self.account_number_last4})>"


class PortfolioSnapshot(Base):
    """Point-in-time portfolio snapshot for a single broker account"""
    __tablename__ = 'portfolio_snapshots'
    
    id = Column(Integer, primary_key=True)
    broker_account_id = Column(Integer, ForeignKey('broker_accounts.id', ondelete='CASCADE'), nullable=False)
    snapshot_date = Column(DateTime, nullable=False)
    total_value = Column(Numeric(15, 2), nullable=False)  # Total portfolio value
    total_positions = Column(Integer, default=0, nullable=False)
    upload_source = Column(String(50), default='csv_upload', nullable=False)
    csv_filename = Column(String(255), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    
    # Relationships
    broker_account = relationship('BrokerAccount', back_populates='portfolio_snapshots')
    holdings = relationship('Holding', back_populates='portfolio_snapshot', cascade='all, delete-orphan')
    aggregate_snapshots = relationship(
        'AggregateSnapshot',
        secondary=aggregate_portfolio_association,
        back_populates='portfolio_snapshots'
    )
    
    # Indexes
    __table_args__ = (
        Index('idx_broker_snapshot_date', 'broker_account_id', 'snapshot_date'),
        Index('idx_snapshot_date', 'snapshot_date'),
    )
    
    def __repr__(self):
        return f"<PortfolioSnapshot(broker_id={self.broker_account_id}, date={self.snapshot_date}, value=${self.total_value})>"


class AggregateSnapshot(Base):
    """Aggregate snapshot combining all broker accounts at a point in time"""
    __tablename__ = 'aggregate_snapshots'
    
    id = Column(Integer, primary_key=True)
    snapshot_date = Column(DateTime, nullable=False)
    total_value = Column(Numeric(15, 2), nullable=False)  # Sum across all brokers
    total_positions = Column(Integer, default=0, nullable=False)  # Sum across all brokers
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    
    # Relationships
    portfolio_snapshots = relationship(
        'PortfolioSnapshot',
        secondary=aggregate_portfolio_association,
        back_populates='aggregate_snapshots'
    )
    risk_metrics = relationship('RiskMetrics', back_populates='aggregate_snapshot', uselist=False, cascade='all, delete-orphan')
    
    # Indexes
    __table_args__ = (
        Index('idx_aggregate_date', 'snapshot_date'),
    )
    
    def __repr__(self):
        return f"<AggregateSnapshot(date={self.snapshot_date}, value=${self.total_value})>"


class Holding(Base):
    """Individual position/holding in a portfolio snapshot"""
    __tablename__ = 'holdings'
    
    id = Column(Integer, primary_key=True)
    portfolio_snapshot_id = Column(Integer, ForeignKey('portfolio_snapshots.id', ondelete='CASCADE'), nullable=False)
    symbol = Column(String(20), nullable=False)
    name = Column(String(255), nullable=True)
    quantity = Column(Numeric(15, 4), nullable=False)
    price = Column(Numeric(15, 4), nullable=False)
    total_value = Column(Numeric(15, 2), nullable=False)
    asset_type = Column(String(50), nullable=False)  # 'stock', 'etf', 'mutual_fund', 'bond', 'cash', 'other'
    account_type = Column(String(50), nullable=True)  # 'taxable', 'ira', '401k', 'roth', etc.
    
    # For ETFs/MFs - store underlying holdings as JSON
    underlying_holdings = Column(Text, nullable=True)  # JSON array: [{"symbol": "AAPL", "weight": 0.05, "value": 1000}, ...]
    underlying_parsed = Column(Boolean, default=False, nullable=False)  # Flag if underlying holdings have been fetched
    
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    
    # Relationships
    portfolio_snapshot = relationship('PortfolioSnapshot', back_populates='holdings')
    
    # Indexes
    __table_args__ = (
        Index('idx_holding_snapshot', 'portfolio_snapshot_id'),
        Index('idx_holding_symbol', 'symbol'),
        Index('idx_holding_asset_type', 'asset_type'),
    )
    
    @property
    def underlying_holdings_list(self):
        """Parse underlying holdings JSON to list"""
        if self.underlying_holdings:
            try:
                return json.loads(self.underlying_holdings)
            except json.JSONDecodeError:
                return []
        return []
    
    @underlying_holdings_list.setter
    def underlying_holdings_list(self, value):
        """Set underlying holdings from list"""
        if value:
            self.underlying_holdings = json.dumps(value)
        else:
            self.underlying_holdings = None
    
    def __repr__(self):
        return f"<Holding(symbol={self.symbol}, qty={self.quantity}, value=${self.total_value})>"


class UnderlyingHolding(Base):
    """Resolved underlying holdings aggregated across all ETFs/MFs in an aggregate snapshot"""
    __tablename__ = 'underlying_holdings'
    
    id = Column(Integer, primary_key=True)
    aggregate_snapshot_id = Column(Integer, ForeignKey('aggregate_snapshots.id', ondelete='CASCADE'), nullable=False)
    symbol = Column(String(20), nullable=False)
    name = Column(String(255), nullable=True)
    total_value = Column(Numeric(15, 2), nullable=False)  # Aggregated value across all sources
    percentage_of_portfolio = Column(Numeric(5, 4), nullable=False)  # e.g., 0.2500 = 25%
    sector = Column(String(100), nullable=True)
    geography = Column(String(100), nullable=True)  # 'US', 'International Developed', 'Emerging Markets', etc.
    
    # Source tracking - which holdings contributed to this
    sources = Column(Text, nullable=True)  # JSON: [{"holding_id": 123, "weight": 0.5, "value": 500}, ...]
    
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    
    # Relationships
    aggregate_snapshot = relationship('AggregateSnapshot')
    
    # Indexes
    __table_args__ = (
        Index('idx_underlying_aggregate', 'aggregate_snapshot_id'),
        Index('idx_underlying_symbol', 'symbol'),
        Index('idx_underlying_percentage', 'percentage_of_portfolio'),
    )
    
    @property
    def sources_list(self):
        """Parse sources JSON to list"""
        if self.sources:
            try:
                return json.loads(self.sources)
            except json.JSONDecodeError:
                return []
        return []
    
    @sources_list.setter
    def sources_list(self, value):
        """Set sources from list"""
        if value:
            self.sources = json.dumps(value)
        else:
            self.sources = None
    
    def __repr__(self):
        return f"<UnderlyingHolding(symbol={self.symbol}, value=${self.total_value}, pct={self.percentage_of_portfolio:.2%})>"


class RiskMetrics(Base):
    """Calculated risk metrics for an aggregate snapshot"""
    __tablename__ = 'risk_metrics'
    
    id = Column(Integer, primary_key=True)
    aggregate_snapshot_id = Column(Integer, ForeignKey('aggregate_snapshots.id', ondelete='CASCADE'), nullable=False, unique=True)
    
    # Stock concentration - stocks exceeding threshold
    concentrated_stocks = Column(Text, nullable=True)  # JSON: [{"symbol": "AAPL", "percentage": 0.25, "value": 50000}, ...]
    concentration_threshold = Column(Numeric(5, 4), default=0.20, nullable=False)  # 0.20 = 20%
    
    # ETF/MF overlap - funds with high overlap
    overlapping_funds = Column(Text, nullable=True)  # JSON: [{"funds": ["VTI", "ITOT"], "overlap_pct": 0.85, ...}, ...]
    overlap_threshold = Column(Numeric(5, 4), default=0.70, nullable=False)  # 0.70 = 70%
    
    # Sector concentration
    sector_breakdown = Column(Text, nullable=True)  # JSON: {"Technology": 0.40, "Healthcare": 0.20, ...}
    
    # Geographic exposure
    geography_breakdown = Column(Text, nullable=True)  # JSON: {"US": 0.70, "International Developed": 0.20, ...}
    
    # Risk level summary
    risk_level = Column(String(20), nullable=True)  # 'low', 'medium', 'high'
    total_risk_flags = Column(Integer, default=0, nullable=False)
    
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    
    # Relationships
    aggregate_snapshot = relationship('AggregateSnapshot', back_populates='risk_metrics')
    
    # Helper methods for JSON fields
    @property
    def concentrated_stocks_list(self):
        if self.concentrated_stocks:
            try:
                return json.loads(self.concentrated_stocks)
            except json.JSONDecodeError:
                return []
        return []
    
    @concentrated_stocks_list.setter
    def concentrated_stocks_list(self, value):
        if value:
            self.concentrated_stocks = json.dumps(value)
        else:
            self.concentrated_stocks = None
    
    @property
    def overlapping_funds_list(self):
        if self.overlapping_funds:
            try:
                return json.loads(self.overlapping_funds)
            except json.JSONDecodeError:
                return []
        return []
    
    @overlapping_funds_list.setter
    def overlapping_funds_list(self, value):
        if value:
            self.overlapping_funds = json.dumps(value)
        else:
            self.overlapping_funds = None
    
    @property
    def sector_breakdown_dict(self):
        if self.sector_breakdown:
            try:
                return json.loads(self.sector_breakdown)
            except json.JSONDecodeError:
                return {}
        return {}
    
    @sector_breakdown_dict.setter
    def sector_breakdown_dict(self, value):
        if value:
            self.sector_breakdown = json.dumps(value)
        else:
            self.sector_breakdown = None
    
    @property
    def geography_breakdown_dict(self):
        if self.geography_breakdown:
            try:
                return json.loads(self.geography_breakdown)
            except json.JSONDecodeError:
                return {}
        return {}
    
    @geography_breakdown_dict.setter
    def geography_breakdown_dict(self, value):
        if value:
            self.geography_breakdown = json.dumps(value)
        else:
            self.geography_breakdown = None
    
    def __repr__(self):
        return f"<RiskMetrics(aggregate_id={self.aggregate_snapshot_id}, risk_level={self.risk_level}, flags={self.total_risk_flags})>"