# MissionControl Splunk AI Assistant — React + Tailwind (No-Build)

This upgrade swaps the static UI for a React 18 + Tailwind UI without any build step (CDN-based), avoiding Vite/Node issues.
- Same FastAPI backend
- Modern React UI with Chart.js line chart
- Works with the same `.env` settings and `MOCK_MODE`

## Run
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn backend.app:app --reload
```
Open http://127.0.0.1:8000
