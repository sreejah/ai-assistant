from .config import settings
import httpx

async def maybe_create_incident(intent, summary, analysis, problem_statement=None):
    if int(settings.MOCK_MODE):
        return {"created": True, "ticket":"INC0012345", "url": (settings.SNOW_INSTANCE or "https://example.service-now.com")+"/nav_to.do?uri=incident.do?sys_id=demo", "message":"Mock incident created (>10% failures)"}
    if not (settings.SNOW_INSTANCE and settings.SNOW_USERNAME and settings.SNOW_PASSWORD):
        return {"created": False, "error": "ServiceNow credentials not configured"}
    short_desc = problem_statement or f"{intent.get('flow')} elevated failures ({summary.get('failure_pct')}%)"
    desc = f"Auto-created by MissionControl bot.\nIntent: {intent}\nSummary: {summary}\nAnalysis: {analysis}"
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.post(
                settings.SNOW_INSTANCE.rstrip('/') + "/api/now/table/incident",
                auth=(settings.SNOW_USERNAME, settings.SNOW_PASSWORD),
                json={"short_description": short_desc, "description": desc, "category":"inquiry","impact":"2","urgency":"2"},
                headers={"Accept":"application/json"}
            )
            r.raise_for_status()
            data = r.json()
            number = data.get("result", {}).get("number", "INC")
            sys_id = data.get("result", {}).get("sys_id", "")
            return {"created": True, "ticket": number, "url": settings.SNOW_INSTANCE.rstrip('/')+f"/nav_to.do?uri=incident.do?sys_id={sys_id}", "message":"Incident created"}
    except Exception as e:
        return {"created": False, "error": str(e)}
