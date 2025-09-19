import os
SN_INSTANCE=https://your-instance.service-now.com
SN_USERNAME=your.user
SN_PASSWORD=your_password

# Optional tweaks
EXCEL_PATH=alerts.xlsx
EXCEL_SHEET=Sheet1
EXCEL_COLUMN=            # leave blank to auto-detect alert name column
SEARCH_FIELDS=display_title,short_description,title
ONLY_PUBLISHED=false     # set true to require published workflow_state
KB_BASE_SYS_ID=          # limit to a specific knowledge base if desired



import sys
import time
import urllib.parse
from typing import List, Dict

import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv(override=True)

# --- ServiceNow config ---
SN_INSTANCE = os.getenv("SN_INSTANCE", "").rstrip("/")
SN_USERNAME = os.getenv("SN_USERNAME")
SN_PASSWORD = os.getenv("SN_PASSWORD")
API_URL = f"{SN_INSTANCE}/api/now/table/kb_knowledge"

# --- Excel config ---
EXCEL_PATH = os.getenv("EXCEL_PATH", "alerts.xlsx")
EXCEL_SHEET = os.getenv("EXCEL_SHEET", "Sheet1")
EXCEL_COLUMN = (os.getenv("EXCEL_COLUMN") or "").strip()

# --- Search config ---
SEARCH_FIELDS = [f.strip() for f in os.getenv(
    "SEARCH_FIELDS", "display_title,short_description,title"
).split(",") if f.strip()]

ONLY_PUBLISHED = os.getenv("ONLY_PUBLISHED", "false").lower() == "true"
KB_BASE_SYS_ID = os.getenv("KB_BASE_SYS_ID", "").strip()

if not SN_INSTANCE or not SN_USERNAME or not SN_PASSWORD:
    print("ERROR: Set SN_INSTANCE, SN_USERNAME, SN_PASSWORD in .env")
    sys.exit(1)

session = requests.Session()
session.auth = (SN_USERNAME, SN_PASSWORD)
session.headers.update({"Accept": "application/json", "Content-Type": "application/json"})
session.timeout = 30


def test_connection() -> None:
    """Check basic connectivity & auth by hitting kb_knowledge with a tiny query."""
    url = API_URL + "?sysparm_fields=sys_id&sysparm_limit=1"
    try:
        r = session.get(url)
        r.raise_for_status()
        print("ServiceNow connection successful.")
    except requests.HTTPError as e:
        print(f"ServiceNow connection failed (HTTP {e.response.status_code}). Details: {e.response.text[:200]}")
        sys.exit(1)
    except Exception as e:
        print(f"ServiceNow connection failed: {e}")
        sys.exit(1)


def find_alert_column(df: pd.DataFrame) -> str:
    """Auto-detect the alert name column if EXCEL_COLUMN isn't set."""
    if EXCEL_COLUMN and EXCEL_COLUMN in df.columns:
        return EXCEL_COLUMN

    # Common variants (case-insensitive)
    candidates = [
        "alert", "alert_name", "alertname", "alert names", "alert_name_column",
        "alert title", "alert_title", "splunk_alert", "name", "alertnames", "Alert Name"
    ]
    lower_map = {c.lower(): c for c in df.columns}
    for c in candidates:
        if c.lower() in lower_map:
            return lower_map[c.lower()]

    # Fallback: first column
    return df.columns[0]


def read_alerts(path: str, sheet: str) -> List[str]:
    df = pd.read_excel(path, sheet_name=sheet)
    col = find_alert_column(df)
    names = [str(x).strip() for x in df[col].dropna() if str(x).strip()]
    if not names:
        raise ValueError(f"No alert names found in column '{col}' of {path}")
    print(f"Using alert name column: '{col}'")
    return names


def build_query(name: str, exact: bool) -> str:
    """Build ServiceNow sysparm_query across multiple fields."""
    parts = ["active=true"]
    if ONLY_PUBLISHED:
        parts.append("workflow_state=published")
    if KB_BASE_SYS_ID:
        parts.append(f"kb_knowledge_base={KB_BASE_SYS_ID}")

    op = "=" if exact else "LIKE"
    for i, field in enumerate(SEARCH_FIELDS):
        prefix = "" if i == 0 else "^OR"
        parts.append(f"{prefix}{field}{op}{name}")
    return "^".join(parts)


def search_kb(name: str) -> Dict[str, str]:
    """
    Check if 'name' is present in kb_knowledge.
    Returns dict with Present ('yes'/'no'), MatchType ('EXACT'/'PARTIAL'/'NOT_FOUND'), and a preview.
    """
    result = {
        "AlertName": name,
        "Present": "no",
        "MatchType": "NOT_FOUND",
        "KB_Number": "",
        "Sys_ID": "",
        "Display_Title": "",
        "Short_Description": "",
        "Workflow_State": "",
        "Active": "",
        "Error": ""
    }

    found_exact = False
    found_partial = False

    for exact in (True, False):
        try:
            q = build_query(name, exact)
            params = {
                "sysparm_fields": "number,sys_id,display_title,short_description,workflow_state,active",
                "sysparm_limit": "10",
                "sysparm_query": q,
            }
            url = API_URL + "?" + urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
            resp = session.get(url)
            resp.raise_for_status()
            items = resp.json().get("result", [])

            if items:
                if exact:
                    # exact if any chosen field equals the query (case-insensitive)
                    for it in items:
                        for f in SEARCH_FIELDS:
                            if str(it.get(f, "")).strip().lower() == name.strip().lower():
                                found_exact = True
                                break
                        if found_exact:
                            break
                else:
                    found_partial = True

                first = items[0]
                result.update({
                    "KB_Number": first.get("number", ""),
                    "Sys_ID": first.get("sys_id", ""),
                    "Display_Title": first.get("display_title", ""),
                    "Short_Description": first.get("short_description", ""),
                    "Workflow_State": first.get("workflow_state", ""),
                    "Active": first.get("active", ""),
                })

            if exact and found_exact:
                break

        except requests.HTTPError as e:
            result["Error"] = f"HTTP {e.response.status_code}: {e.response.text[:180]}"
            break
        except Exception as e:
            result["Error"] = str(e)
            break
        finally:
            time.sleep(0.15)

    if found_exact:
        result["Present"] = "yes"
        result["MatchType"] = "EXACT"
    elif found_partial:
        result["Present"] = "yes"
        result["MatchType"] = "PARTIAL"
    else:
        result["Present"] = "no"
        result["MatchType"] = "NOT_FOUND"

    return result


def main():
    test_connection()  # prints "ServiceNow connection successful." on success

    try:
        names = read_alerts(EXCEL_PATH, EXCEL_SHEET)
    except Exception as e:
        print(f"ERROR reading Excel: {e}")
        sys.exit(1)

    print("\nChecking alert names in ServiceNow Knowledge...\n")

    out_rows = []
    for nm in names:
        res = search_kb(nm)
        if res["Error"]:
            print(f"[ERROR] {nm}: {res['Error']}")
        else:
            # Per request: print 'yes' if present, otherwise 'no'
            print(f"{nm}: {res['Present']}")
        out_rows.append(res)

    # Save results for reference
    out_df = pd.DataFrame(out_rows)
    out_xlsx = "alerts_results.xlsx"
    with pd.ExcelWriter(out_xlsx, engine="openpyxl") as w:
        out_df.to_excel(w, index=False, sheet_name="Results")

    print(f"\nSaved results to {out_xlsx}")


if __name__ == "__main__":
    main()
