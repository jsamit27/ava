# Quick Start Guide - Web Interface

## Local Testing

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Set environment variables (optional, defaults are in code):**
   ```bash
   export AVA_USER="amit"
   export AVA_PASS="sta6952907"
   ```

3. **Run the application:**
   ```bash
   python app.py
   ```
   Or:
   ```bash
   uvicorn app:app --host 0.0.0.0 --port 5000
   ```

4. **Open your browser:**
   Visit: http://localhost:8080

5. **Initialize session:**
   - Enter your SQLite database path (e.g., `sandbox_lead_1.db`)
   - Enter Lead ID
   - Enter Buyer ID
   - Enter Escalation Phone Number
   - Click "Start Chat"

6. **Start chatting:**
   - Type your message and press Enter or click Send
   - Ava will respond just like in the CLI version

## What's Different from CLI?

- **Web Interface**: Beautiful, modern chat UI instead of terminal
- **Session Management**: Each browser session gets a unique session ID
- **Same Functionality**: All the same tools and features as the CLI version

## Files Created

- `app.py` - FastAPI web application
- `templates/index.html` - Frontend chat interface
- `requirements.txt` - Python dependencies
- `render.yaml` - Render deployment configuration
- `README_DEPLOY.md` - Detailed deployment instructions

## Next Steps

See `README_DEPLOY.md` for instructions on deploying to Render.

