# Database Migration Guide: SQLite to PostgreSQL

This guide will help you migrate your data from `sandbox_lead_3.db` (SQLite) to your PostgreSQL database on Render.

## Prerequisites

1. ✅ PostgreSQL database created on Render
2. ✅ `DATABASE_URL` environment variable set in Render (already done)
3. ✅ `sandbox_lead_3.db` file in your local project directory

## Step 1: Get Your PostgreSQL Connection String

1. Go to your Render dashboard
2. Click on your PostgreSQL database
3. Find the **"Internal Database URL"** (for Render services) or **"External Database URL"** (for local access)
4. Copy the connection string (looks like: `postgresql://user:password@host:port/database`)

## Step 2: Run the Migration Script Locally

### Option A: Set Environment Variable and Run

```bash
# Set the DATABASE_URL (use External Database URL from Render)
export DATABASE_URL="postgresql://user:password@host:port/database"

# Run the migration script
python migrate_to_postgres.py
```

### Option B: Run with Inline Environment Variable

```bash
# Replace with your actual External Database URL from Render
DATABASE_URL="postgresql://user:password@host:port/database" python migrate_to_postgres.py
```

## What the Script Does

1. ✅ Connects to both SQLite and PostgreSQL databases
2. ✅ Creates all tables in PostgreSQL (matching your SQLite schema)
3. ✅ Migrates all data from SQLite to PostgreSQL in the correct order:
   - `leads` (no dependencies)
   - `buyers` (no dependencies)
   - `cars` (depends on leads)
   - `lead_buyer_map` (depends on leads and buyers)
   - `pickup` (depends on cars)
   - `buyer_schedule` (depends on buyers)

## Step 3: Verify Migration

After migration, you can verify the data:

```bash
# Connect to your PostgreSQL database
psql "postgresql://user:password@host:port/database"

# Check row counts
SELECT 'leads' as table_name, COUNT(*) FROM leads
UNION ALL
SELECT 'buyers', COUNT(*) FROM buyers
UNION ALL
SELECT 'cars', COUNT(*) FROM cars
UNION ALL
SELECT 'lead_buyer_map', COUNT(*) FROM lead_buyer_map
UNION ALL
SELECT 'pickup', COUNT(*) FROM pickup
UNION ALL
SELECT 'buyer_schedule', COUNT(*) FROM buyer_schedule;
```

## Troubleshooting

### Error: "psycopg2-binary not installed"
```bash
pip install psycopg2-binary
```

### Error: "Could not connect to PostgreSQL"
- Make sure you're using the **External Database URL** (not Internal)
- Check that your IP is whitelisted in Render (if required)
- Verify the connection string is correct

### Error: "Foreign key constraint violation"
- The script migrates tables in dependency order, so this shouldn't happen
- If it does, check that all referenced IDs exist in parent tables

## Notes

- The script will **drop and recreate** all tables in PostgreSQL, so make sure you're migrating to a fresh/empty database
- For tables with `SERIAL PRIMARY KEY`, the script will let PostgreSQL generate new IDs
- For tables with `INTEGER PRIMARY KEY` (like `cars` and `pickup`), it preserves the original IDs
- All data types are preserved (TEXT, INTEGER, etc.)

## After Migration

Once migration is complete:
1. ✅ Your Render app will automatically use PostgreSQL (via `DATABASE_URL`)
2. ✅ All your existing data will be available
3. ✅ New data added through Render will persist permanently

