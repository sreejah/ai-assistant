from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional
from dotenv import load_dotenv
import os, traceback

from .utils.config import settings
from .utils.nlp import parse_user_command, build_spl_query
from .utils.splunk_connector import (
    run_oneshot_search,
    mock_splunk_results,
    run_failed_urlpaths,
    run_prev_day_timechart,
)
from .utils.ai_analysis import analyze_results_with_ai, fallback_analysis
from .utils.snow_integration import maybe_create_incident

load_dotenv()
app = FastAPI(title="MissionControl Splunk AI Assistant")

frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")
static_path = os.path.join(frontend_dir, "static")
os.makedirs(static_path, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_path), name="static")

@app.middleware("http")
async def error_wrapper(request: Request, call_next):
    try:
        return await call_next(request)
    except Exception as e:
        tb = traceback.format_exc()
        print(tb)
        return JSONResponse(status_code=500, content={"error": str(e), "traceback": tb.splitlines()[-6:]})

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

    spl, where = build_spl_query(intent)

    if int(settings.MOCK_MODE):
        mock = mock_splunk_results(intent)
        summary = mock.get("summary", {})
        timechart = mock.get("timechart", [])
        prevday_timechart = mock.get("prevday_timechart", [])
        failed_urlpaths = mock.get("failed_urlpaths", [])
    else:
        results = run_oneshot_search(spl)
        summary = results.get("summary", {})
        timechart = results.get("timechart", [])
        failed_urlpaths = run_failed_urlpaths(intent["index"], intent["window_minutes"], where)
        prevday_timechart = run_prev_day_timechart(intent["index"], intent["window_minutes"], where)

    analysis = await analyze_results_with_ai(intent=intent, summary=summary, timechart=timechart)
    if analysis is None:
        analysis = fallback_analysis(intent=intent, summary=summary, timechart=timechart)

    incident = None
    if summary and float(summary.get("failure_pct", 0)) > 10.0:
        incident = await maybe_create_incident(
            intent=intent, summary=summary, analysis=analysis,
            problem_statement=req.problem_statement
        )

    return JSONResponse({
        "intent": intent,
        "spl": spl,
        "summary": summary,
        "timechart": timechart,
        "prevday_timechart": prevday_timechart,
        "failed_urlpaths": failed_urlpaths,
        "analysis": analysis,
        "incident": incident
    })
