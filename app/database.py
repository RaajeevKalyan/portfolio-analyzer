"""
Database Configuration and Session Management
"""
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker, scoped_session, declarative_base
from sqlalchemy.pool import StaticPool
import os
import logging

logger = logging.getLogger(__name__)

# Create declarative base for models
Base = declarative_base()

# Database engine (singleton)
_engine = None
_session_factory = None


def get_engine():
    """Get or create database engine"""
    global _engine
    
    if _engine is None:
        database_url = os.getenv('DATABASE_URL', 'sqlite:///data/portfolio.db')
        
        # SQLite-specific configuration
        connect_args = {}
        if database_url.startswith('sqlite'):
            connect_args = {
                'check_same_thread': False,  # Allow multi-threaded access
                'timeout': 30  # Lock timeout in seconds
            }
        
        _engine = create_engine(
            database_url,
            echo=False,  # Set to True for SQL query debugging
            pool_pre_ping=True,  # Verify connections before using
            connect_args=connect_args,
            # Use StaticPool for SQLite to prevent "database is locked" errors
            poolclass=StaticPool if database_url.startswith('sqlite') else None
        )
        
        # Enable foreign keys for SQLite
        if database_url.startswith('sqlite'):
            @event.listens_for(Engine, "connect")
            def set_sqlite_pragma(dbapi_conn, connection_record):
                cursor = dbapi_conn.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.execute("PRAGMA journal_mode=WAL")  # Write-Ahead Logging for better concurrency
                cursor.close()
        
        logger.info(f"Database engine created: {database_url}")
    
    return _engine


def get_session_factory():
    """Get or create session factory"""
    global _session_factory
    
    if _session_factory is None:
        engine = get_engine()
        _session_factory = scoped_session(
            sessionmaker(
                bind=engine,
                autocommit=False,
                autoflush=False,
                expire_on_commit=False
            )
        )
        logger.info("Session factory created")
    
    return _session_factory


def get_session():
    """Get a new database session"""
    Session = get_session_factory()
    return Session()


def init_db():
    """Initialize database - create all tables"""
    from app.models import (
        UserSettings,
        BrokerAccount,
        PortfolioSnapshot,
        AggregateSnapshot,
        Holding,
        UnderlyingHolding,
        RiskMetrics
    )
    
    engine = get_engine()
    Base.metadata.create_all(engine)
    logger.info("Database tables created")
    
    # Create default user settings if not exists
    session = get_session()
    try:
        settings = session.query(UserSettings).first()
        if not settings:
            settings = UserSettings(
                snapshot_retention_limit=25,
                theme_preference='light'
            )
            session.add(settings)
            session.commit()
            logger.info("Default user settings created")
    except Exception as e:
        session.rollback()
        logger.error(f"Error creating default settings: {e}")
    finally:
        session.close()


def close_db():
    """Close database connections"""
    global _session_factory, _engine
    
    if _session_factory:
        _session_factory.remove()
        _session_factory = None
    
    if _engine:
        _engine.dispose()
        _engine = None
    
    logger.info("Database connections closed")


# Context manager for sessions
class db_session:
    """Context manager for database sessions"""
    
    def __enter__(self):
        self.session = get_session()
        return self.session
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self.session.rollback()
        else:
            self.session.commit()
        self.session.close()