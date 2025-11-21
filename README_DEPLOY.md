# Deploying GMTV Ava Assistant to Render

This guide will help you deploy the FastAPI web application to Render.

## Prerequisites

1. A Render account (sign up at https://render.com)
2. Your code pushed to a Git repository (GitHub, GitLab, or Bitbucket)

## Deployment Steps

### 1. Prepare Your Repository

Make sure all files are committed and pushed to your Git repository:
- `app.py` - FastAPI application
- `requirements.txt` - Python dependencies
- `templates/index.html` - Frontend HTML
- All your existing code files (`agent_controller.py`, `tools.py`, `all_tools.py`, etc.)

### 2. Create a New Web Service on Render

1. Go to your Render dashboard: https://dashboard.render.com
2. Click "New +" and select "Web Service"
3. Connect your Git repository
4. Configure the service:
   - **Name**: `gmtv-ava-assistant` (or any name you prefer)
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn app:app --host 0.0.0.0 --port $PORT`

### 3. Set Environment Variables

In the Render dashboard, go to your service's "Environment" tab and add:

**Required:**
- `AVA_USER` - Your Ava API username
- `AVA_PASS` - Your Ava API password

**Optional (if using Google Maps or RingCentral):**
- `GOOGLE_MAPS_API_KEY` - For location services
- `RINGCENTRAL_CLIENT_ID` - RingCentral API client ID
- `RINGCENTRAL_CLIENT_SECRET` - RingCentral API client secret
- `RINGCENTRAL_USERNAME` - RingCentral username
- `RINGCENTRAL_PASSWORD` - RingCentral password
- `RINGCENTRAL_SERVER` - RingCentral server URL

**Auto-generated:**
- `FLASK_SECRET_KEY` - Can be auto-generated or set manually

### 4. Deploy

1. Click "Create Web Service"
2. Render will automatically build and deploy your application
3. Once deployed, you'll get a URL like: `https://gmtv-ava-assistant.onrender.com`

### 5. Upload Database Files

**Important**: Your SQLite database files need to be accessible. You have a few options:

**Option A: Upload to a cloud storage service**
- Upload your `.db` files to AWS S3, Google Cloud Storage, or similar
- Modify `all_tools.py` to download the database file when needed
- Or use a remote database (PostgreSQL, MySQL) instead of SQLite

**Option B: Include in repository (not recommended for production)**
- Add your database files to the repository
- Note: This is not ideal for production as databases should not be in version control

**Option C: Use Render's persistent disk (if available)**
- Some Render plans support persistent storage
- Store database files in a persistent directory

### 6. Access Your Application

Once deployed, visit your Render URL and you should see the chat interface.

## Local Testing

Before deploying, test locally:

```bash
# Install dependencies
pip install -r requirements.txt

# Run the application
uvicorn app:app --host 0.0.0.0 --port 5000

# Or use the included main block
python app.py
```

Then visit: http://localhost:5000

## Troubleshooting

### Database File Not Found
- Make sure database files are accessible
- Consider using a remote database for production

### Environment Variables Not Set
- Double-check all required environment variables are set in Render dashboard
- Restart the service after adding new environment variables

### Port Issues
- Render automatically sets the `PORT` environment variable
- Make sure your start command uses `$PORT` or `uvicorn` will use the default

### Build Failures
- Check the build logs in Render dashboard
- Ensure all dependencies in `requirements.txt` are correct
- Python version compatibility issues? Check Render's Python version

## Notes

- Render free tier services spin down after 15 minutes of inactivity
- First request after spin-down may take 30-60 seconds
- Consider upgrading to a paid plan for always-on service
- For production, consider using a proper database (PostgreSQL) instead of SQLite

