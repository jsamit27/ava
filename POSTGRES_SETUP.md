# Setting Up PostgreSQL on Render (Free & Persistent)

## Step 1: Create PostgreSQL Database on Render

1. Go to your Render dashboard: https://dashboard.render.com
2. Click **"New +"** → **"PostgreSQL"**
3. Configure:
   - **Name**: `gmtv-ava-db` (or any name)
   - **Database**: `gmtv_ava` (or any name)
   - **User**: `gmtv_user` (or any name)
   - **Region**: Choose closest to you
   - **Plan**: **Free** (90 days free, then $7/month - but you can export data before then)
4. Click **"Create Database"**
5. Wait for it to provision (takes ~2 minutes)

## Step 2: Get Connection String

Once created, you'll see:
- **Internal Database URL**: `postgresql://user:password@host:port/dbname`
- **External Connection String**: (for connecting from outside Render)

**Copy the Internal Database URL** - you'll need this!

## Step 3: Add Environment Variable to Your Web Service

1. Go to your web service (the FastAPI app) on Render
2. Go to **"Environment"** tab
3. Add new environment variable:
   - **Key**: `DATABASE_URL`
   - **Value**: Paste the Internal Database URL from Step 2
4. Click **"Save Changes"**

## Step 4: Update requirements.txt

Add this line:
```
psycopg2-binary>=2.9.0
```

## Step 5: Migrate Your SQLite Data (Optional)

If you want to copy existing data from `sandbox_lead_3.db`:

1. Install PostgreSQL client locally: `brew install postgresql` (Mac) or download from postgresql.org
2. Export from SQLite:
   ```bash
   sqlite3 sandbox_lead_3.db .dump > dump.sql
   ```
3. Convert SQLite dump to PostgreSQL format (remove SQLite-specific syntax)
4. Import to PostgreSQL using the connection string

**Or start fresh** - the code will work with an empty database and you can add data through the app.

## Step 6: Deploy

1. Commit and push your code changes
2. Render will auto-deploy
3. Your database is now persistent! ✅

## Benefits

- ✅ **Persistent** - Changes survive restarts
- ✅ **Free tier** - 90 days free, then $7/month
- ✅ **Easy** - Managed by Render, no setup needed
- ✅ **Reliable** - Production-grade database

## Cost

- **Free for 90 days**
- **$7/month** after (or export your data and switch to another free service)

## Alternative Free Options (if you want to avoid cost)

1. **Supabase** - Free PostgreSQL (500MB, unlimited time)
2. **Neon** - Free PostgreSQL tier
3. **Railway** - Free PostgreSQL tier

But Render PostgreSQL is the easiest since you're already on Render!

