from .config import settings
import httpx

async def analyze_results_with_ai(intent, summary, timechart):
    api_key = (settings.OPENAI_API_KEY or "").strip()
    if not api_key or int(settings.MOCK_MODE):
        return None
    prompt = (
        "You are a payments SRE assistant.\n"
        f"Flow: {intent}\n"
        f"Summary: {summary}\n"
        f"Timechart (first 5): {timechart[:5]}\n"
        "Explain what’s happening, likely causes (<=3), and first checks. <=120 words."
    )
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": "gpt-4o-mini",
                    "messages": [
                        {"role":"system","content":"You are concise and production-minded."},
                        {"role":"user","content": prompt}
                    ],
                    "temperature": 0.2,
                    "max_tokens": 200
                }
            )
            r.raise_for_status()
            data = r.json()
            return data["choices"][0]["message"]["content"].strip()
    except Exception:
        return None

def fallback_analysis(intent, summary, timechart):
    succ = summary.get("success", 0); fail = summary.get("failure", 0)
    pct = summary.get("failure_pct", 0.0); flow = intent.get("flow"); partner = intent.get("partner")
    sev = "High" if pct>20 else ("Elevated" if pct>10 else "Normal")
    who = f" for '{partner}'" if partner else ""
    return (f"{flow} shows {fail}/{succ+fail} failures ({pct}%). Severity: {sev}{who}. "
            "Check deploys, timeouts, upstream errors, and auth/latency anomalies.")
