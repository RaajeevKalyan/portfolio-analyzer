#!/usr/bin/env python3
"""
Database Initialization Script

This script creates all database tables and initializes default settings.
Run this script to set up the database for the first time.

Usage:
    python scripts/init_db.py
"""
import sys
import os

# Add parent directory to path to import app modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.database import init_db, get_engine, get_session
from app.models import (
    UserSettings,
    BrokerAccount,
    PortfolioSnapshot,
    AggregateSnapshot,
    Holding,
    UnderlyingHolding,
    RiskMetrics
)
from sqlalchemy import inspect
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def check_database_exists():
    """Check if database file exists"""
    database_url = os.getenv('DATABASE_URL', 'sqlite:///data/portfolio.db')
    
    if database_url.startswith('sqlite:///'):
        db_path = database_url.replace('sqlite:///', '')
        return os.path.exists(db_path)
    
    # For non-SQLite databases, assume we can connect
    return True


def check_tables_exist():
    """Check if tables already exist"""
    try:
        engine = get_engine()
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        
        expected_tables = [
            'user_settings',
            'broker_accounts',
            'portfolio_snapshots',
            'aggregate_snapshots',
            'holdings',
            'underlying_holdings',
            'risk_metrics',
            'aggregate_portfolio_association'
        ]
        
        existing = [t for t in expected_tables if t in tables]
        return len(existing) > 0, existing
    except Exception as e:
        logger.error(f"Error checking tables: {e}")
        return False, []


def create_sample_data():
    """Create sample data for testing (optional)"""
    from datetime import datetime
    from decimal import Decimal
    
    session = get_session()
    
    try:
        # Check if sample data already exists
        existing_accounts = session.query(BrokerAccount).count()
        if existing_accounts > 0:
            logger.info("Sample data already exists, skipping...")
            return
        
        logger.info("Creating sample data...")
        
        # Create sample broker account
        merrill_account = BrokerAccount(
            broker_name='merrill',
            account_number_last4='1234',
            account_nickname='My Merrill Account',
            is_active=True
        )
        session.add(merrill_account)
        session.flush()  # Get ID without committing
        
        # Create sample portfolio snapshot
        snapshot = PortfolioSnapshot(
            broker_account_id=merrill_account.id,
            snapshot_date=datetime.utcnow(),
            total_value=Decimal('100000.00'),
            total_positions=3,
            upload_source='csv_upload',
            csv_filename='sample_portfolio.csv'
        )
        session.add(snapshot)
        session.flush()
        
        # Create sample holdings
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
                asset_type='etf',
                underlying_parsed=False
            ),
            Holding(
                portfolio_snapshot_id=snapshot.id,
                symbol='MSFT',
                name='Microsoft Corporation',
                quantity=Decimal('100'),
                price=Decimal('380.00'),
                total_value=Decimal('38000.00'),
                asset_type='stock'
            )
        ]
        
        for holding in holdings:
            session.add(holding)
        
        session.commit()
        logger.info("Sample data created successfully!")
        logger.info(f"  - Broker Account: {merrill_account.broker_name} (***{merrill_account.account_number_last4})")
        logger.info(f"  - Portfolio Snapshot: ${snapshot.total_value}")
        logger.info(f"  - Holdings: {len(holdings)} positions")
        
    except Exception as e:
        session.rollback()
        logger.error(f"Error creating sample data: {e}")
        raise
    finally:
        session.close()


def main():
    """Main initialization function"""
    logger.info("=" * 60)
    logger.info("Portfolio Risk Analyzer - Database Initialization")
    logger.info("=" * 60)
    
    # Check if database exists
    db_exists = check_database_exists()
    logger.info(f"Database exists: {db_exists}")
    
    # Check if tables exist
    tables_exist, existing_tables = check_tables_exist()
    
    if tables_exist:
        logger.warning("Database tables already exist!")
        logger.info(f"Existing tables: {', '.join(existing_tables)}")
        
        response = input("\nDo you want to recreate the database? This will DELETE ALL DATA! (yes/no): ")
        if response.lower() != 'yes':
            logger.info("Initialization cancelled.")
            return
        
        logger.warning("Recreating database tables...")
        from app.database import Base
        engine = get_engine()
        Base.metadata.drop_all(engine)
        logger.info("Existing tables dropped.")
    
    # Initialize database
    logger.info("Creating database tables...")
    init_db()
    logger.info("✓ Database tables created successfully!")
    
    # Verify tables
    tables_exist, existing_tables = check_tables_exist()
    logger.info(f"✓ Created {len(existing_tables)} tables:")
    for table in existing_tables:
        logger.info(f"    - {table}")
    
    # Ask if user wants sample data
    response = input("\nDo you want to create sample data for testing? (yes/no): ")
    if response.lower() == 'yes':
        create_sample_data()
    
    logger.info("")
    logger.info("=" * 60)
    logger.info("Database initialization complete!")
    logger.info("=" * 60)
    logger.info("")
    logger.info("Next steps:")
    logger.info("  1. Start the application: docker-compose up -d")
    logger.info("  2. Access at: https://localhost:8443")
    logger.info("  3. Upload CSV files from your brokers")
    logger.info("")


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        logger.info("\nInitialization cancelled by user.")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Initialization failed: {e}")
        sys.exit(1)