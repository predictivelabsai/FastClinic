from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

def get_database_url(env=None):
    """Get database URL based on environment selection"""
    if env is None:
        env = os.getenv('DEFAULT_ENV', 'LIVE')
    if env == 'DEV':
        return os.getenv('DEV_DB_URL')
    return os.getenv('LIVE_DB_URL')

# Create engine with dynamic DATABASE_URL
def create_db_engine(env=None):
    DATABASE_URL = get_database_url(env)
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL is not set. Please configure DEV_DB_URL/LIVE_DB_URL and DEFAULT_ENV.")
    # SQLite (e.g., in-memory) engines don't accept pool_size/max_overflow with the default pool
    if DATABASE_URL.startswith("sqlite"):
        return create_engine(DATABASE_URL)
    return create_engine(DATABASE_URL, pool_size=5, max_overflow=10)

# Instead of creating the engine once at import time, we'll create it dynamically
def get_session(env=None):
    """Get a session factory that uses the current environment setting"""
    engine = create_db_engine(env)
    session_factory = sessionmaker(bind=engine)
    return scoped_session(session_factory)

# Get a thread-safe session using the current environment
def get_db():
    """Get a new database session"""
    db = get_session()()
    try:
        yield db
    finally:
        db.close()

# For backward compatibility with existing code
Session = property(lambda: get_session())
