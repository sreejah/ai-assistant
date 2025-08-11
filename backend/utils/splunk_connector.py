from .config import settings

def _maybe_import_splunk():
    try:
        import splunklib.client as client
        import splunklib.results as results
        return client, results
    except Exception:
        return None, None

def run_oneshot_search(spl_query: str):
    client, results = _maybe_import_splunk()
    if client is None:
        raise RuntimeError("splunklib not available. Install 'splunk-sdk'.")
    service = client.connect(
        host=settings.SPLUNK_HOST,
        port=settings.SPLUNK_PORT,
        username=settings.SPLUNK_USERNAME,
        password=settings.SPLUNK_PASSWORD,
        scheme="https",
        verify=bool(int(settings.SPLUNK_VERIFY_SSL)),
    )
    oneshot = service.jobs.oneshot(spl_query, output_mode='json')
    import json
    payload = json.loads(oneshot.read().decode('utf-8'))
    rows = payload.get("results", [])
    timechart, ts, tf = [], 0, 0
    for r in rows:
        t = r.get("_time"); s = int(float(r.get("success", 0))); f = int(float(r.get("failure", 0)))
        timechart.append({"_time": t, "success": s, "failure": f})
        ts += s; tf += f
    denom = ts + tf
    pct = round(100.0 * tf / denom, 2) if denom else 0.0
    return {"summary": {"success": ts, "failure": tf, "failure_pct": pct}, "timechart": timechart}

def mock_splunk_results(intent: dict):
    import random, datetime
    random.seed(7)
    buckets = max(1, intent.get("window_minutes", 60)//5)
    base_success = 55
    base_failure = 3 if intent["flow"] != "apigatwey" else 7
    now = datetime.datetime.utcnow()
    tc = []
    for i in range(buckets):
        s = max(0, base_success + random.randint(-6, 6))
        f = max(0, base_failure + random.randint(-2, 7))
        t = (now - datetime.timedelta(minutes=5*(buckets-i))).isoformat() + "Z"
        tc.append({"_time": t, "success": s, "failure": f})
    ts = sum(p["success"] for p in tc); tf = sum(p["failure"] for p in tc)
    denom = ts + tf; pct = round(100.0 * tf / denom, 2) if denom else 0.0
    return {"summary": {"success": ts, "failure": tf, "failure_pct": pct}, "timechart": tc}
