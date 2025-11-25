# Quick PostgreSQL Setup for Persistent Database

## Why PostgreSQL?
- ✅ **Persistent** - Changes survive restarts on Render
- ✅ **Free for 90 days** on Render
- ✅ **Easy setup** - Just create database and add one environment variable
- ✅ **Works with your existing code** (with small updates)

## Quick Setup (5 minutes)

### 1. Create PostgreSQL Database on Render
1. Go to https://dashboard.render.com
2. Click **"New +"** → **"PostgreSQL"**
3. Name it: `gmtv-ava-db`
4. Choose **Free** plan
5. Click **"Create Database"**
6. Wait ~2 minutes

### 2. Copy the Connection String
- After creation, you'll see **"Internal Database URL"**
- It looks like: `postgresql://user:pass@host:port/dbname`
- **Copy this!**

### 3. Add to Your Web Service
1. Go to your web service (FastAPI app)
2. **Environment** tab
3. Add: `DATABASE_URL` = (paste the connection string)
4. **Save**

### 4. Deploy
- Code is already updated in `requirements.txt` (psycopg2-binary added)
- Just push to GitHub and Render will auto-deploy

## What Happens Next?

**Option A: Start Fresh (Easiest)**
- Database starts empty
- Add cars through the app
- All changes persist! ✅

**Option B: Migrate Existing Data**
- Export from SQLite: `sqlite3 sandbox_lead_3.db .dump > data.sql`
- Convert to PostgreSQL format
- Import using `psql` or pgAdmin

## Code Changes Needed

The code needs small updates to use PostgreSQL. Currently it uses SQLite. 

**For now:** The code will still work with SQLite locally (CLI) and will use PostgreSQL on Render if `DATABASE_URL` is set.

**To fully enable PostgreSQL:** Update functions in `all_tools.py` to use `db_connection.py` helper (see example in the code).

## Cost
- **Free for 90 days**
- **$7/month** after (or export data and switch to another free service like Supabase)

## Alternative Free Options
- **Supabase** - Free forever (500MB limit)
- **Neon** - Free tier available
- **Railway** - Free tier available

But Render PostgreSQL is easiest since you're already there!

