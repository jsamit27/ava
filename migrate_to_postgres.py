#!/usr/bin/env python3
"""
Migration script to migrate data from SQLite (sandbox_lead_3.db) to PostgreSQL.
This script will:
1. Read all data from SQLite
2. Create tables in PostgreSQL
3. Insert all data into PostgreSQL
"""

import os
import sqlite3
import sys
from typing import Dict, List, Any

# Try to import PostgreSQL
try:
    import psycopg2
    POSTGRES_AVAILABLE = True
except ImportError:
    POSTGRES_AVAILABLE = False
    print("ERROR: psycopg2-binary not installed. Run: pip install psycopg2-binary")
    sys.exit(1)

# Get database URLs
SQLITE_PATH = "sandbox_lead_3.db"
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    print("ERROR: DATABASE_URL environment variable not set.")
    print("Please set it to your PostgreSQL connection string from Render.")
    print("Example: postgresql://user:password@host:port/database")
    sys.exit(1)

def get_sqlite_connection():
    """Connect to SQLite database."""
    if not os.path.exists(SQLITE_PATH):
        print(f"ERROR: SQLite database not found: {SQLITE_PATH}")
        sys.exit(1)
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def get_postgres_connection():
    """Connect to PostgreSQL database."""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except Exception as e:
        print(f"ERROR: Could not connect to PostgreSQL: {e}")
        sys.exit(1)

def create_postgres_schema(pg_conn):
    """Create all tables in PostgreSQL."""
    cur = pg_conn.cursor()
    
    # Drop tables if they exist (in reverse order of dependencies)
    print("Dropping existing tables if they exist...")
    tables = ['buyer_schedule', 'pickup', 'lead_buyer_map', 'cars', 'buyers', 'leads']
    for table in tables:
        cur.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
    
    pg_conn.commit()
    print("Creating tables...")
    
    # Create leads table
    cur.execute("""
        CREATE TABLE leads (
            id SERIAL PRIMARY KEY,
            first_name TEXT,
            last_name TEXT,
            phone TEXT,
            email TEXT,
            chat_logs TEXT,
            created_at TEXT
        )
    """)
    
    # Create buyers table
    cur.execute("""
        CREATE TABLE buyers (
            id SERIAL PRIMARY KEY,
            first_name TEXT,
            last_name TEXT,
            phone_number TEXT,
            created_at TEXT
        )
    """)
    
    # Create cars table
    cur.execute("""
        CREATE TABLE cars (
            id INTEGER PRIMARY KEY,
            vin TEXT,
            year INTEGER,
            make TEXT,
            model TEXT,
            trim TEXT,
            mileage INTEGER,
            interior_condition TEXT,
            exterior_condition TEXT,
            seller_ask_cents INTEGER,
            buyer_offer_cents INTEGER,
            created_at TEXT,
            lead_id INTEGER,
            FOREIGN KEY(lead_id) REFERENCES leads(id)
        )
    """)
    
    # Create unique index on VIN
    cur.execute("""
        CREATE UNIQUE INDEX idx_cars_vin_unique ON cars(vin)
    """)
    
    # Create lead_buyer_map table
    cur.execute("""
        CREATE TABLE lead_buyer_map (
            id SERIAL PRIMARY KEY,
            lead_id INTEGER,
            buyer_id INTEGER,
            FOREIGN KEY(lead_id) REFERENCES leads(id),
            FOREIGN KEY(buyer_id) REFERENCES buyers(id)
        )
    """)
    
    # Create pickup table
    cur.execute("""
        CREATE TABLE pickup (
            pick_up_id INTEGER PRIMARY KEY,
            car_id INTEGER,
            address TEXT,
            contact_phone TEXT,
            pick_up_info TEXT,
            created_at TEXT,
            dropoff_time TEXT,
            FOREIGN KEY(car_id) REFERENCES cars(id)
        )
    """)
    
    # Create buyer_schedule table
    cur.execute("""
        CREATE TABLE buyer_schedule (
            id SERIAL PRIMARY KEY,
            buyer_id INTEGER NOT NULL,
            description TEXT NOT NULL,
            schedule_time TEXT NOT NULL,
            priority TEXT CHECK (priority IN ('Low','Medium','High')) DEFAULT 'Medium'
        )
    """)
    
    pg_conn.commit()
    print("✓ Tables created successfully!")

def migrate_table(sqlite_conn, pg_conn, table_name: str, columns: List[str], preserve_ids: bool = True):
    """Migrate data from SQLite to PostgreSQL for a single table.
    
    Args:
        preserve_ids: If True, preserves original IDs (needed for foreign keys).
                      If False, lets PostgreSQL generate new IDs.
    """
    print(f"\nMigrating {table_name}...")
    
    # Read from SQLite
    sqlite_cur = sqlite_conn.cursor()
    sqlite_cur.execute(f"SELECT * FROM {table_name}")
    rows = sqlite_cur.fetchall()
    
    if not rows:
        print(f"  No data in {table_name}, skipping...")
        return
    
    print(f"  Found {len(rows)} rows")
    
    # Prepare data for insertion
    pg_cur = pg_conn.cursor()
    
    # Build INSERT statement and determine which columns to use
    if preserve_ids:
        # Include id column to preserve foreign key relationships
        insert_cols = columns
        placeholders = ', '.join(['%s'] * len(columns))
        insert_sql = f"INSERT INTO {table_name} ({', '.join(columns)}) VALUES ({placeholders})"
    else:
        # Exclude id and let PostgreSQL generate it
        insert_cols = [col for col in columns if col != 'id']
        placeholders = ', '.join(['%s'] * len(insert_cols))
        insert_sql = f"INSERT INTO {table_name} ({', '.join(insert_cols)}) VALUES ({placeholders})"
    
    # Convert rows to tuples
    data_to_insert = []
    max_id = None
    for row in rows:
        row_dict = dict(row)
        if not preserve_ids and 'id' in row_dict:
            # Remove id if we're not preserving it
            row_dict.pop('id', None)
        else:
            # Track max ID for sequence reset
            if preserve_ids and 'id' in row_dict and row_dict.get('id'):
                current_id = row_dict.get('id')
                if max_id is None or current_id > max_id:
                    max_id = current_id
        values = tuple(row_dict.get(col, None) for col in insert_cols)
        data_to_insert.append(values)
    
    # Insert data
    try:
        # Use executemany for batch insertion
        pg_cur.executemany(insert_sql, data_to_insert)
        
        # Reset sequence if we preserved IDs (only for SERIAL columns, not INTEGER PRIMARY KEY)
        # Check if sequence exists before trying to reset it
        if preserve_ids and 'id' in columns and max_id:
            sequence_name = f"{table_name}_id_seq"
            # Check if sequence exists
            pg_cur.execute("""
                SELECT EXISTS (
                    SELECT 1 FROM pg_class WHERE relname = %s
                )
            """, (sequence_name,))
            sequence_exists = pg_cur.fetchone()[0]
            
            if sequence_exists:
                reset_seq_sql = f"SELECT setval('{sequence_name}', {max_id}, true)"
                pg_cur.execute(reset_seq_sql)
        
        pg_conn.commit()
        print(f"  ✓ Inserted {len(data_to_insert)} rows")
    except Exception as e:
        pg_conn.rollback()
        print(f"  ✗ Error inserting data: {e}")
        raise

def main():
    print("=" * 60)
    print("SQLite to PostgreSQL Migration Script")
    print("=" * 60)
    print(f"SQLite source: {SQLITE_PATH}")
    print(f"PostgreSQL target: {DATABASE_URL.split('@')[1] if '@' in DATABASE_URL else 'hidden'}")
    print()
    
    # Connect to databases
    print("Connecting to databases...")
    sqlite_conn = get_sqlite_connection()
    pg_conn = get_postgres_connection()
    print("✓ Connected to both databases")
    
    try:
        # Create schema
        create_postgres_schema(pg_conn)
        
        # Migrate data in dependency order
        # preserve_ids=True to maintain foreign key relationships
        # 1. Leads (no dependencies, but cars reference lead_id)
        migrate_table(sqlite_conn, pg_conn, 'leads', 
                     ['id', 'first_name', 'last_name', 'phone', 'email', 'chat_logs', 'created_at'],
                     preserve_ids=True)
        
        # 2. Buyers (no dependencies, but buyer_schedule references buyer_id)
        migrate_table(sqlite_conn, pg_conn, 'buyers',
                     ['id', 'first_name', 'last_name', 'phone_number', 'created_at'],
                     preserve_ids=True)
        
        # 3. Cars (depends on leads, preserves IDs for pickup references)
        migrate_table(sqlite_conn, pg_conn, 'cars',
                     ['id', 'vin', 'year', 'make', 'model', 'trim', 'mileage',
                      'interior_condition', 'exterior_condition', 'seller_ask_cents',
                      'buyer_offer_cents', 'created_at', 'lead_id'],
                     preserve_ids=True)
        
        # 4. Lead_buyer_map (depends on leads and buyers, IDs not critical)
        migrate_table(sqlite_conn, pg_conn, 'lead_buyer_map',
                     ['id', 'lead_id', 'buyer_id'],
                     preserve_ids=False)
        
        # 5. Pickup (depends on cars, preserves pick_up_id)
        migrate_table(sqlite_conn, pg_conn, 'pickup',
                     ['pick_up_id', 'car_id', 'address', 'contact_phone', 
                      'pick_up_info', 'created_at', 'dropoff_time'],
                     preserve_ids=True)
        
        # 6. Buyer_schedule (depends on buyers, IDs not critical)
        migrate_table(sqlite_conn, pg_conn, 'buyer_schedule',
                     ['id', 'buyer_id', 'description', 'schedule_time', 'priority'],
                     preserve_ids=False)
        
        print("\n" + "=" * 60)
        print("✓ Migration completed successfully!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n✗ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        sqlite_conn.close()
        pg_conn.close()
        print("\nDatabase connections closed.")

if __name__ == "__main__":
    main()

