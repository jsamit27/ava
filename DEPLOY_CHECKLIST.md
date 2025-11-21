# Render Deployment Checklist

## Before Deploying

- [ ] Code is pushed to GitHub/GitLab/Bitbucket
- [ ] All dependencies are in `requirements.txt`
- [ ] `app.py` is the main application file
- [ ] Tested locally with `python app.py`

## Render Setup

- [ ] Created Render account
- [ ] Connected GitHub account
- [ ] Created new Web Service
- [ ] Set build command: `pip install -r requirements.txt`
- [ ] Set start command: `uvicorn app:app --host 0.0.0.0 --port $PORT`

## Environment Variables

- [ ] `AVA_USER` - Your Ava API username
- [ ] `AVA_PASS` - Your Ava API password
- [ ] (Optional) `GOOGLE_MAPS_API_KEY`
- [ ] (Optional) `RINGCENTRAL_CLIENT_ID`
- [ ] (Optional) `RINGCENTRAL_CLIENT_SECRET`
- [ ] (Optional) `RINGCENTRAL_USERNAME`
- [ ] (Optional) `RINGCENTRAL_PASSWORD`
- [ ] (Optional) `RINGCENTRAL_SERVER`

## Database Setup

Choose one:
- [ ] Option A: Upload `.db` files to cloud storage (S3, etc.)
- [ ] Option B: Use Render PostgreSQL instead of SQLite
- [ ] Option C: Include small test DBs in repo (not for production)

## After Deployment

- [ ] Test the deployed URL
- [ ] Verify environment variables are working
- [ ] Test chat functionality
- [ ] Check logs for any errors

## Quick Commands

```bash
# Test locally first
python app.py

# Or with uvicorn
uvicorn app:app --host 0.0.0.0 --port 8080
```

