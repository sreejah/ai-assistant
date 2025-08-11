import re
from datetime import timedelta

FLOW_TO_INDEX = {
    "billpay": 88082,
    "bill pay": 88082,
    "quickdeposit": 88082,
    "quick deposit": 88082,
    "transfer": 88082,
    "apigateway": 102212,
    "apigatwey": 102212,
}

FLOW_TO_FILTER = {
    "billpay": 'urlpath="billpay" OR service="billpay"',
    "bill pay": 'urlpath="billpay" OR service="billpay"',
    "quick deposit": 'urlpath="quickdeposit" OR service="quickdeposit"',
    "quickdeposit": 'urlpath="quickdeposit" OR service="quickdeposit"',
    "transfer": 'urlpath="transfer" OR service="transfer"',
}

def parse_window(text: str) -> int:
    text = text.lower()
    m = re.search(r"last\s+(\d+)\s*(min|mins|minutes?)", text)
    if m: return int(m.group(1))
    m = re.search(r"last\s+(\d+)\s*(hour|hours|hr|hrs)", text)
    if m: return int(m.group(1)) * 60
    if "last 24 hours" in text: return 24 * 60
    return 60

def parse_user_command(text: str) -> dict:
    t = text.strip().lower()
    partner = None
    if "apigatwey" in t or "apigateway" in t:
        flow = "apigatwey"
        idx = FLOW_TO_INDEX[flow]
        m = re.search(r"for\s+([a-z0-9_-]+)", t)
        if m: partner = m.group(1)
    else:
        if "bill pay" in t or "billpay" in t: flow = "billpay"
        elif "quick deposit" in t or "quickdeposit" in t or "quickpay" in t: flow = "quickdeposit"
        elif "transfer" in t: flow = "transfer"
        else: return {"error": "Unknown flow. Try: billpay, quickdeposit, transfer, or apigatwey for <partner>."}
        idx = FLOW_TO_INDEX[flow]
    window_minutes = parse_window(t)
    return {"flow": flow, "index": idx, "window_minutes": window_minutes, "partner": partner}

def build_spl_query(intent: dict) -> str:
    index = intent["index"]
    window = intent["window_minutes"]
    if intent["flow"] in ("apigateway", "apigatwey"):
        vendor = intent.get("partner") or "*"
        base_filter = f'(vendor="{vendor}" OR partner="{vendor}")' if vendor and vendor != "*" else ""
        where = base_filter
    else:
        flow_key = "quick deposit" if intent["flow"] == "quickdeposit" else intent["flow"]
        where = FLOW_TO_FILTER.get(flow_key, "")
    spl = f"""search index={index} earliest=-{window}m latest=now {where}
| eval outcome=if(status>=400 OR like(error, "%error%") OR like(error, "%fail%"), "failure", "success")
| bin _time span=5m
| stats count(eval(outcome="success")) as success count(eval(outcome="failure")) as failure by _time
| eventstats sum(success) as total_success sum(failure) as total_failure
| eval failure_pct=round(100.0*total_failure/nullif(total_success+total_failure,0),2)
| sort _time""".strip()
    return spl
