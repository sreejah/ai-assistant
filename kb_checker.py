
SN_INSTANCE=https://your-instance.service-now.com
SN_USERNAME=your.user
SN_PASSWORD=your_password

# Optional tweaks (defaults shown)
EXCEL_PATH=knowledge_list.xlsx
EXCEL_SHEET=Sheet1
EXCEL_NAME_COLUMN=ArticleName
SEARCH_FIELDS=short_description,display_title # comma-separated kb_knowledge fields to search


import os
import sys
import time
import json
import urllib.parse
from typing import Dict, List, Tuple, Optional

import pandas as pd
import requests
from dotenv import load_dotenv

# ---------------------------
# Config & helpers
# ---------------------------
load_dotenv(override=True)

SN_INSTANCE = os.getenv("SN_INSTANCE", "").rstrip("/")
SN_USERNAME = os.getenv("SN_USERNAME")
SN_PASSWORD = os.getenv("SN_PASSWORD")

EXCEL_PATH = os.getenv("EXCEL_PATH", "knowledge_list.xlsx")
EXCEL_SHEET = os.getenv("EXCEL_SHEET", "Sheet1")
EXCEL_NAME_COLUMN = os.getenv("EXCEL_NAME_COLUMN", "ArticleName")
SEARCH_FIELDS = [f.strip() for f in os.getenv("SEARCH_FIELDS", "short_description,display_title").split(",") if f.strip()]

API_BASE = f"{SN_INSTANCE}/api/now/table/kb_knowledge"

# Safety checks
if not SN_INSTANCE or not SN_USERNAME or not SN_PASSWORD:
    print("ERROR: Please set SN_INSTANCE, SN_USERNAME and SN_PASSWORD in your .env file.")
    sys.exit(1)

HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json",
}

SESSION = requests.Session()
SESSION.auth = (SN_USERNAME, SN_PASSWORD)
SESSION.headers.update(HEADERS)
SESSION.timeout = 30  # seconds


def build_sysparm_query(name: str, exact: bool = False) -> str:
    """
    Build a ServiceNow sysparm_query that searches across multiple fields.
    - exact=False: uses LIKE
    - exact=True: uses '=' (exact match)
    Also enforces active=true and (optionally) published states if you want.
    """
    if not SEARCH_FIELDS:
        raise ValueError("No SEARCH_FIELDS configured.")

    clauses = []
    op = "=" if exact else "LIKE"
    for i, field in enumerate(SEARCH_FIELDS):
        # First field goes as-is; subsequent fields are OR'd
        prefix = "" if i == 0 else "^OR"
        # URL-unsafe values are fine here; SNOW expects raw operators. We will url-encode the entire query later.
        clauses.append(f"{prefix}{field}{op}{name}")

    # Filter for active + (optionally) published. If your instance uses a different workflow field, tweak here.
    # Common options: workflow_state=published OR valid_toISEMPTY^ORvalid_to>{today}
    # We'll keep it simple with active=true and allow any workflow state.
    base = "active=true"
    return base + "^" + "".join(clauses)


def query_kb(name: str) -> Dict[str, any]:
    """
    Query SNOW for a given article name, returning:
      - available_exact: bool
      - available_partial: bool
      - matches: list of matched records (subset of fields)
    """
    results = {
        "name": name,
        "available_exact": False,
        "available_partial": False,
        "matches": [],  # each item: {number, sys_id, short_description, display_title, workflow_state}
        "error": None,
    }

    for exact in (True, False):
        try:
            sysparm_query = build_sysparm_query(name, exact=exact)
            params = {
                # Return a small set of useful fields. Add more if you need them.
                "sysparm_fields": "number,sys_id,short_description,display_title,workflow_state,active",
                "sysparm_limit": "10",
                "sysparm_query": sysparm_query,
            }
            # Encode query safely
            url = API_BASE + "?" + urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
            resp = SESSION.get(url)
            resp.raise_for_status()
            data = resp.json()

            # SNOW returns {"result": [...]}
            matches = data.get("result", [])
            # Normalize & store
            for m in matches:
                results["matches"].append({
                    "number": m.get("number"),
                    "sys_id": m.get("sys_id"),
                    "short_description": m.get("short_description"),
                    "display_title": m.get("display_title"),
                    "workflow_state": m.get("workflow_state"),
                    "active": m.get("active"),
                })

            if exact:
                # Mark exact availability if any record's chosen field(s) equals the name (case-insensitive)
                for m in matches:
                    for field in SEARCH_FIELDS:
                        val = (m.get(field) or "").strip()
                        if val.lower() == name.strip().lower():
                            results["available_exact"] = True
                            break
                    if results["available_exact"]:
                        break
            else:
                results["available_partial"] = len(matches) > 0

        except requests.HTTPError as e:
            results["error"] = f"HTTP {e.response.status_code}: {e.response.text[:200]}"
            break
        except Exception as e:
            results["error"] = str(e)
            break

        # Gentle pacing to avoid rate limits
        time.sleep(0.15)

    return results


def read_article_names_from_excel(path: str, sheet: str, column: str) -> List[str]:
    df = pd.read_excel(path, sheet_name=sheet)
    if column not in df.columns:
        raise ValueError(f"Column '{column}' not found in sheet '{sheet}'. Columns: {list(df.columns)}")
    # Coerce to str and drop NaNs/empties
    names = [str(x).strip() for x in df[column].dropna().tolist() if str(x).strip()]
    return names


def main():
    try:
        names = read_article_names_from_excel(EXCEL_PATH, EXCEL_SHEET, EXCEL_NAME_COLUMN)
    except Exception as e:
        print(f"ERROR reading Excel: {e}")
        sys.exit(1)

    if not names:
        print("No article names found in the Excel file.")
        sys.exit(0)

    print(f"Checking {len(names)} knowledge article name(s) against ServiceNow...\n")

    rows = []
    for name in names:
        res = query_kb(name)
        if res["error"]:
            print(f"[ERROR] {name}: {res['error']}")
        else:
            status = (
                "EXACT MATCH" if res["available_exact"]
                else ("PARTIAL MATCH" if res["available_partial"] else "NOT FOUND")
            )
            # Show a small preview of the first match
            preview = ""
            if res["matches"]:
                m = res["matches"][0]
                preview = f"{m.get('number') or ''} | {m.get('short_description') or m.get('display_title') or ''}"

            print(f"[{status}] {name}" + (f"  ->  {preview}" if preview else ""))

        # Prepare CSV row(s)
        if res["matches"]:
            for m in res["matches"]:
                rows.append({
                    "QueryName": res["name"],
                    "Status": "EXACT" if res["available_exact"] else ("PARTIAL" if res["available_partial"] else "NOT_FOUND"),
                    "KB_Number": m.get("number"),
                    "Sys_ID": m.get("sys_id"),
                    "Short_Description": m.get("short_description"),
                    "Display_Title": m.get("display_title"),
                    "Workflow_State": m.get("workflow_state"),
                    "Active": m.get("active"),
                })
        else:
            rows.append({
                "QueryName": res["name"],
                "Status": "NOT_FOUND" if not (res["available_exact"] or res["available_partial"]) else ("EXACT" if res["available_exact"] else "PARTIAL"),
                "KB_Number": "",
                "Sys_ID": "",
                "Short_Description": "",
                "Display_Title": "",
                "Workflow_State": "",
                "Active": "",
            })

    out_csv = "snow_kb_check_results.csv"
    pd.DataFrame(rows).to_csv(out_csv, index=False)
    print(f"\nReport written to {out_csv}")


if __name__ == "__main__":
    main()
