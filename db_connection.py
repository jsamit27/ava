# db_connection.py
"""
Database connection helper that supports both SQLite (for local CLI) and PostgreSQL (for Render).
Automatically detects which database type to use based on the connection string.
"""
import os
from typing import Optional, Any, Dict, Tuple
import logging

logger = logging.getLogger(__name__)

# Try to import database libraries
try:
    import sqlite3
    SQLITE_AVAILABLE = True
except ImportError:
    SQLITE_AVAILABLE = False

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    POSTGRES_AVAILABLE = True
except ImportError:
    POSTGRES_AVAILABLE = False

def is_postgres(connection_string: str) -> bool:
    """Check if connection string is PostgreSQL."""
    return connection_string.startswith(('postgresql://', 'postgres://'))

def get_db_connection(connection_string: str):
    """
    Get a database connection (SQLite or PostgreSQL).
    
    Args:
        connection_string: Either a file path (for SQLite) or PostgreSQL URL (postgresql://...)
    
    Returns:
        Tuple of (connection, is_postgres_flag)
    """
    # Check if it's a PostgreSQL URL
    if is_postgres(connection_string):
        if not POSTGRES_AVAILABLE:
            raise RuntimeError("PostgreSQL support not available. Install psycopg2-binary: pip install psycopg2-binary")
        
        conn = psycopg2.connect(connection_string)
        return conn, True
    
    # Otherwise, treat as SQLite file path
    if not SQLITE_AVAILABLE:
        raise RuntimeError("SQLite support not available")
    
    conn = sqlite3.connect(connection_string)
    conn.row_factory = sqlite3.Row
    return conn, False

def execute_query(conn, is_postgres_flag: bool, query: str, params: tuple = ()):
    """
    Execute a query and return a cursor.
    Handles differences between SQLite and PostgreSQL.
    """
    if is_postgres_flag:
        # PostgreSQL - use %s instead of ? for placeholders
        pg_query = query.replace('?', '%s')
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(pg_query, params)
        return cur
    else:
        # SQLite
        return conn.execute(query, params)

def get_connection_string() -> str:
    """
    Get database connection string from environment or default to SQLite.
    For Render: Use DATABASE_URL environment variable
    For local: Use sqlite_path from SESSION or default file
    """
    # Check for PostgreSQL URL in environment (Render)
    db_url = os.getenv("DATABASE_URL")
    if db_url:
        return db_url
    
    # Fall back to SQLite (for local CLI)
    from tools import SESSION
    sqlite_path = SESSION.get("sqlite_path")
    if sqlite_path:
        return sqlite_path
    
    # Default fallback
    return "sandbox_lead_3.db"

