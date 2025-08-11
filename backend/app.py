from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional
from dotenv import load_dotenv
import os
from backend.utils.config import settings
from backend.utils.nlp import parse_user_command, build_spl_query
from backend.utils.splunk_connector import run_oneshot_search, mock_splunk_results
from backend.utils.ai_analysis import analyze_results_with_ai, fallback_analysis
from backend.utils.snow_integration import maybe_create_incident

load_dotenv()
app = FastAPI(title="MissionControl Splunk AI Assistant (React)")

frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")
app.mount("/static", StaticFiles(directory=os.path.join(frontend_dir, "static")), name="static")

@app.get("/", response_class=HTMLResponse)
async def index():
    with open(os.path.join(frontend_dir, "index.html"), "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())

class RunRequest(BaseModel):
    query: str
    problem_statement: Optional[str] = None

@app.post("/api/run")
async def run_query(req: RunRequest):
    intent = parse_user_command(req.query)
    if intent.get("error"):
        raise HTTPException(status_code=400, detail=intent["error"])

    spl = build_spl_query(intent)
    if settings.MOCK_MODE:
        results = mock_splunk_results(intent)
    else:
        results = run_oneshot_search(spl)

    summary = results.get("summary", {})
    timechart = results.get("timechart", [])

    analysis = await analyze_results_with_ai(intent=intent, summary=summary, timechart=timechart)
    if analysis is None:
        analysis = fallback_analysis(intent=intent, summary=summary, timechart=timechart)

    incident = None
    if summary and summary.get("failure_pct", 0) > 10.0:
        incident = await maybe_create_incident(
            intent=intent,
            summary=summary,
            analysis=analysis,
            problem_statement=req.problem_statement
        )

    return JSONResponse({
        "intent": intent,
        "spl": spl,
        "summary": summary,
        "timechart": timechart,
        "analysis": analysis,
        "incident": incident
    })
