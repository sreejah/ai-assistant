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
        timechart.append({"_time": t, "success": s, "failure": f}); ts += s; tf += f
    denom = ts + tf; pct = round(100.0 * tf / denom, 2) if denom else 0.0
    return {"summary": {"success": ts, "failure": tf, "failure_pct": pct}, "timechart": timechart}

def run_failed_urlpaths(index: int, window_minutes: int, where: str = ""):
    spl = f'''search index={index} earliest=-{window_minutes}m latest=now {where}
| eval outcome=if(status>=400 OR like(error, "%error%") OR like(error, "%fail%"), "failure", "success")
| search outcome="failure"
| stats count as failure_count by urlpath
| sort - failure_count
| head 50'''
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
    oneshot = service.jobs.oneshot(spl, output_mode='json')
    import json
    payload = json.loads(oneshot.read().decode('utf-8'))
    rows = payload.get("results", [])
    return [{"urlpath": r.get("urlpath") or "-", "failure_count": int(float(r.get("failure_count", 0)))} for r in rows]

def run_prev_day_timechart(index: int, window_minutes: int, where: str = ""):
    earliest = -(window_minutes + 1440)
    latest = -1440
    spl = f'''search index={index} earliest={earliest}m latest={latest}m {where}
| eval outcome=if(status>=400 OR like(error, "%error%") OR like(error, "%fail%"), "failure", "success")
| bin _time span=5m
| stats count(eval(outcome="success")) as success count(eval(outcome="failure")) as failure by _time
| sort _time'''
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
    oneshot = service.jobs.oneshot(spl, output_mode='json')
    import json
    payload = json.loads(oneshot.read().decode('utf-8'))
    rows = payload.get("results", [])
    prev_tc = []
    for r in rows:
        prev_tc.append({
            "_time": r.get("_time"),
            "success": int(float(r.get("success", 0))),
            "failure": int(float(r.get("failure", 0))),
        })
    return prev_tc

def mock_splunk_results(intent: dict):
    import random, datetime
    random.seed(42)
    window = int(intent.get("window_minutes", 60))
    buckets = max(1, window // 5)
    flow = (intent.get("flow") or "").lower()
    base_success = 50
    base_failure = 6 if flow in ("apigateway", "apigatwey") else 2
    now = datetime.datetime.utcnow()

    timechart = []
    for i in range(buckets):
        s = max(0, base_success + random.randint(-5, 5))
        f = max(0, base_failure + random.randint(-2, 6))
        t = (now - datetime.timedelta(minutes=5*(buckets-i))).isoformat()+"Z"
        timechart.append({"_time": t, "success": s, "failure": f})

    random.seed(99)
    prevday_timechart = []
    for i in range(buckets):
        s = max(0, base_success + random.randint(-6, 6))
        f = max(0, base_failure + random.randint(-3, 7))
        t = (now - datetime.timedelta(days=1, minutes=5*(buckets-i))).isoformat()+"Z"
        prevday_timechart.append({"_time": t, "success": s, "failure": f})

    failed_urlpaths = [
        {"urlpath": "/api/v1/billpay/submit", "failure_count": 18},
        {"urlpath": "/api/v1/billpay/confirm", "failure_count": 11},
        {"urlpath": "/api/v1/transfer/init", "failure_count": 7},
    ]

    ts = sum(p["success"] for p in timechart)
    tf = sum(p["failure"] for p in timechart)
    denom = ts + tf
    pct = round(100.0 * tf / denom, 2) if denom else 0.0

    return {
        "summary": {"success": ts, "failure": tf, "failure_pct": pct},
        "timechart": timechart,
        "prevday_timechart": prevday_timechart,
        "failed_urlpaths": failed_urlpaths,
    }
