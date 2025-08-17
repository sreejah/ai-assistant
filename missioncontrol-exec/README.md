# MissionControl Splunk AI Assistant — Executable Package

FastAPI backend + React (CDN) frontend. Shows:
- Summary (success/failure/failure%)
- Trend (Current Window) line chart
- Trend (Previous Day — Same Window) line chart
- Top Failed URL Paths table with counts
- AI Analysis (OpenAI optional)
- Auto-create ServiceNow incident if failure% > 10 (mock enabled when MOCK_MODE=1)

## Quick Start
```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # leave MOCK_MODE=1 for demo
uvicorn backend.app:app --reload
```
Open http://127.0.0.1:8000

## Commands to try
- `check billpay for last 60 min`
- `check apigatwey for amazon for last 30 min`

## Notes
- This package includes `frontend/static/` so StaticFiles mount is happy.
- If you want to use real Splunk, set `MOCK_MODE=0` and configure Splunk env vars.
