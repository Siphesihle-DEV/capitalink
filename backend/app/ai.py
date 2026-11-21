"""Gemini adapter. Gemini reads the documents; averages, volatility and findings are then computed here in code, so the numbers are consistent.
Never approves, pays or touches balances."""
import os, json, base64, statistics as st, httpx
from typing import Optional
from pydantic import BaseModel, Field

class AIError(Exception): pass

class Month(BaseModel):
    month: str = ""; deposits: float = 0; withdrawals: float = 0

class Assessment(BaseModel):
    summary: str = ""
    monthly: list[Month] = Field(default_factory=list)
    months_covered: int = 0
    avg_monthly_deposits: Optional[float] = None
    avg_monthly_withdrawals: Optional[float] = None
    est_monthly_revenue: Optional[float] = None
    est_monthly_expenses: Optional[float] = None
    existing_debt_payments: Optional[float] = None
    revenue_consistency: str = ""
    cashflow_patterns: list[str] = Field(default_factory=list)
    unusual_transactions: list[str] = Field(default_factory=list)
    positives: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    inconsistencies: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    confidence: str = "low"
    limitations: str = "Figures are extracted by AI from the uploaded documents and are not verified facts."

PROMPT = """You are a credit analyst assistant for a South African SME financing platform. Read the attached bank statements (all amounts are in South African rand, ZAR).
Return ONLY one JSON object, no markdown, with exactly these keys:
{"summary": "3-4 plain-language sentences about the business's cash flow",
 "monthly": [{"month": "YYYY-MM", "deposits": number, "withdrawals": number}],
 "existing_debt_payments": number or null,
 "cashflow_patterns": [strings], "unusual_transactions": [strings], "positives": [strings], "risks": [strings],
 "missing_information": [strings], "inconsistencies": [strings], "suggestions": [strings], "confidence": "low|medium|high"}
Rules:
- "monthly": one entry per calendar month that appears in the statements. deposits = total of all credits that month; withdrawals = total of all debits that month. Exclude transfers between the business's own accounts if you can identify them. Plain numbers, no currency symbols or thousands separators.
- "existing_debt_payments": the average monthly total of loan, vehicle finance, credit facility or other debt instalments you can identify, otherwise null.
- Only use what is in the documents. Never invent figures; if something is unclear, say so under missing_information.
- Do not approve or reject anything and do not predict default.
- "inconsistencies": differences between the declared business profile below and the statements.
Declared business profile: """

def _parts(profile, files):
    parts = [{"text": PROMPT + json.dumps(profile, default=str)}]
    for mime, data, name in files:
        if mime == "text/csv": parts.append({"text": f"Bank statement file {name} (CSV):\n" + data.decode("utf-8", "ignore")[:300_000]})
        else: parts.append({"inline_data": {"mime_type": mime, "data": base64.b64encode(data).decode()}})
    return parts

def _call(key, parts):
    models = [m for m in [os.getenv("GEMINI_MODEL"), "gemini-2.5-flash", "gemini-2.0-flash", "gemini-flash-latest"] if m]
    last = ""
    for model in dict.fromkeys(models):
        try:
            r = httpx.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent", headers={"x-goog-api-key": key}, timeout=180,
                           json={"contents": [{"parts": parts}], "generationConfig": {"responseMimeType": "application/json", "temperature": 0, "maxOutputTokens": 8192}})
        except httpx.HTTPError as e:
            raise AIError(f"Could not reach Gemini ({type(e).__name__}). Check the internet connection.")
        if r.status_code == 404: last = f"model {model} not available"; continue  # try the next model
        if r.status_code >= 400:
            msg = (r.json().get("error") or {}).get("message", r.text[:200]) if r.content else str(r.status_code)
            raise AIError(f"Gemini error {r.status_code} ({model}): {msg}")
        data = r.json(); cands = data.get("candidates") or []
        if not cands or not (cands[0].get("content") or {}).get("parts"):
            raise AIError("Gemini returned no answer for these documents (they may be unreadable or blocked). Try a clearer PDF.")
        return "".join(p.get("text", "") for p in cands[0]["content"]["parts"])
    raise AIError(f"No Gemini model was available ({last}). Set GEMINI_MODEL to a model your key can use.")

def parse(text):
    a, b = text.find("{"), text.rfind("}")
    if a < 0 or b < a: raise AIError("Gemini did not return structured data. Please try again.")
    try: return Assessment.model_validate(json.loads(text[a:b + 1]))
    except Exception as e: raise AIError(f"Gemini returned data in an unexpected format ({type(e).__name__}). Please try again.")

def enrich(a: Assessment) -> Assessment:
    ms = [m for m in a.monthly if m.deposits or m.withdrawals]
    a.months_covered = len(ms)
    if not ms:
        a.missing_information.append("No monthly figures could be read from the documents"); return a
    dep, wd = [m.deposits for m in ms], [m.withdrawals for m in ms]
    a.avg_monthly_deposits, a.avg_monthly_withdrawals = round(st.mean(dep), 2), round(st.mean(wd), 2)
    a.est_monthly_revenue = a.avg_monthly_deposits
    a.est_monthly_expenses = round(max(a.avg_monthly_withdrawals - (a.existing_debt_payments or 0), 0), 2)
    cv = st.pstdev(dep) / st.mean(dep) if len(dep) > 1 and st.mean(dep) > 0 else 0
    a.revenue_consistency = f"{'Consistent' if cv <= 0.2 else 'Moderately variable' if cv <= 0.4 else 'Highly variable'} (month-to-month variation {cv * 100:.0f}%)"
    if len(ms) < 12: a.missing_information.append(f"Only {len(ms)} of the last 12 months were found in the statements")
    if cv > 0.4: a.risks.append(f"Deposits vary widely from month to month ({cv * 100:.0f}% variation)")
    elif cv <= 0.2 and len(ms) >= 6: a.positives.append(f"Stable monthly deposits over {len(ms)} months")
    if a.avg_monthly_withdrawals > a.avg_monthly_deposits * 0.95: a.risks.append("Withdrawals use up nearly all deposits, leaving little room for repayments")
    elif a.avg_monthly_deposits > 0: a.positives.append(f"Deposits exceed withdrawals by about {(1 - a.avg_monthly_withdrawals / a.avg_monthly_deposits) * 100:.0f}% on average")
    a.limitations += " Deposits are used as a proxy for revenue and may include non-sales credits."
    return a

def analyze(profile: dict, files: list) -> Assessment:
    key = os.getenv("GEMINI_API_KEY")
    if not key: raise AIError("Gemini is not configured. Add GEMINI_API_KEY to the backend .env and restart.")
    if not files: raise AIError("No documents to analyse. Upload a bank statement first.")
    return enrich(parse(_call(key, _parts(profile, files))))
