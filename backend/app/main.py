import os, json, hashlib, hmac, base64, time, uuid, datetime as dt
from decimal import Decimal
from typing import Optional
import jwt
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel
from .db import *
from . import ledger, ai, payments, chain, storage, sbauth
from .ledger import D, q

app = FastAPI(title="CapitaLink API")
app.add_middleware(CORSMiddleware, allow_origins=os.getenv("CORS_ORIGINS", "*").split(","), allow_methods=["*"], allow_headers=["*"])
JWT_SECRET = os.getenv("JWT_SECRET", "dev-only-change-me")
ALLOWED = {"application/pdf", "image/png", "image/jpeg", "text/csv"}
init_db()

def get_db():
    s = SessionLocal()
    try: yield s
    finally: s.close()

def hash_pw(p, salt=None):
    salt = salt or os.urandom(8).hex()
    return salt + "$" + hashlib.pbkdf2_hmac("sha256", p.encode(), salt.encode(), 100_000).hex()
def check_pw(p, stored): return hmac.compare_digest(hash_pw(p, stored.split("$")[0]), stored)

def user_dep(*roles):
    def dep(request: Request, s=Depends(get_db)):
        tok = request.headers.get("authorization", "").removeprefix("Bearer ")
        try: u = s.get(User, sbauth.verify(tok) if sbauth.enabled() else jwt.decode(tok, JWT_SECRET, algorithms=["HS256"])["sub"])
        except Exception as e:
            sbauth.log.warning("401 %s: %s: %s", request.url.path, type(e).__name__, e); raise HTTPException(401, "Sign in required")
        if not u or (roles and u.role not in roles): raise HTTPException(403, "Not allowed for your role")
        return u
    return dep

def commit(s):
    try: s.commit()
    except Exception: s.rollback(); raise

# ---------- auth ----------
class Reg(BaseModel): email: str; password: str; name: str; role: str
class Login(BaseModel): email: str; password: str
def userinfo(u): return {"id": u.id, "name": u.name, "email": u.email, "role": u.role, "demo": bool(u.is_demo)}
def tokenize(u, token=None): return {"token": token or jwt.encode({"sub": u.id, "exp": int(time.time()) + 86400}, JWT_SECRET, "HS256"), "user": userinfo(u)}

@app.get("/health")
def health(): return {"ok": True, "gemini": bool(os.getenv("GEMINI_API_KEY")),
                      "chain": bool(os.getenv("REGISTRY_ADDRESS")), "auth": "supabase" if sbauth.enabled() else "local", "payments": payments.PROVIDER(), "environment": payments.environment(),
                      "storage": "supabase" if os.getenv("SUPABASE_URL") else "local", "db": "postgres" if IS_PG else "sqlite"}

@app.post("/auth/register")
def register(b: Reg, s=Depends(get_db)):
    if b.role not in ("investor", "sme"): raise HTTPException(400, "Role must be investor or sme")
    if len(b.password) < 8: raise HTTPException(400, "Password must be at least 8 characters")
    if s.query(User).filter(User.email == b.email.lower()).first(): raise HTTPException(409, "Email already registered")
    if sbauth.enabled():  # Supabase owns credentials and email verification; role is assigned here, never taken from the client token
        sid, session = sbauth.signup(b.email.lower(), b.password, b.name)
        u = User(id=sid, email=b.email.lower(), name=b.name, pw="supabase-auth", role=b.role); s.add(u); commit(s)
        return tokenize(u, session["access_token"]) if session else {"message": "Check your email to confirm your account, then sign in."}
    u = User(email=b.email.lower(), name=b.name, pw=hash_pw(b.password), role=b.role); s.add(u); commit(s)
    return tokenize(u)

@app.post("/auth/login")
def login(b: Login, s=Depends(get_db)):
    if sbauth.enabled():
        sid, tok = sbauth.login(b.email.lower(), b.password); u = s.get(User, sid)
        if not u: raise HTTPException(403, "Account is not set up on this platform")
        return tokenize(u, tok)
    u = s.query(User).filter(User.email == b.email.lower()).first()
    if not u or not check_pw(b.password, u.pw): raise HTTPException(401, "Wrong email or password")
    return tokenize(u)

class Reset(BaseModel): email: str
@app.post("/auth/reset")
def reset(b: Reset):
    if sbauth.enabled(): sbauth.recover(b.email.lower())
    return {"message": "If that email is registered, a reset link has been sent."}

@app.get("/industries")
def industries(): return INDUSTRIES

def row(o, *skip): return {c.name: (str(getattr(o, c.name)) if isinstance(getattr(o, c.name), (Decimal, dt.date, dt.datetime)) else getattr(o, c.name))
                           for c in o.__table__.columns if c.name not in skip}

# ---------- payments ----------
def order_out(o): return {**row(o), "description": payments.describe(o), "checkout": payments.checkout_info(o)}

@app.get("/payments/{ref}")
def get_order(ref: str, u=Depends(user_dep()), s=Depends(get_db)):
    o = s.query(PaymentOrder).filter(PaymentOrder.ref == ref).first()
    if not o or o.user_id != u.id: raise HTTPException(404, "Payment not found")
    return order_out(o)

class PayBody(BaseModel): method: str = "eft"; bank: Optional[str] = None; outcome: str = "PAID"
@app.post("/payments/{ref}/pay")
def pay_order(ref: str, b: PayBody, u=Depends(user_dep()), s=Depends(get_db)):
    o = s.query(PaymentOrder).filter(PaymentOrder.ref == ref).first()
    if not o or o.user_id != u.id: raise HTTPException(404, "Payment not found")
    if payments.PROVIDER() != "sandbox": raise HTTPException(400, "This payment is completed on the payment provider's page")
    if b.outcome == "PAID" and b.method == "eft" and not b.bank: raise HTTPException(400, "Choose your bank")
    try: res = payments.sandbox_pay(s, o, b.outcome.upper()); commit(s)
    except ValueError as e: s.rollback(); raise HTTPException(400, str(e))
    return {"result": res, "order": order_out(o)}

@app.post("/payments/webhook/payfast")
async def payfast_webhook(request: Request, s=Depends(get_db)):
    try: res = payments.payfast_itn(s, await request.body()); commit(s)
    except PermissionError as e: raise HTTPException(401, str(e))
    except (LookupError, ValueError) as e: s.rollback(); raise HTTPException(400, str(e))
    return {"result": res}

# ---------- investor ----------
class Contrib(BaseModel): industry: str; amount: Decimal

@app.post("/investor/contribute")
def contribute(b: Contrib, u=Depends(user_dep("investor")), s=Depends(get_db)):
    if b.industry not in INDUSTRIES: raise HTTPException(400, "Unknown industry")
    if b.amount <= 0: raise HTTPException(400, "Amount must be positive")
    try: o = payments.create_order(s, "contribution", u.id, b.amount, industry=b.industry)
    except NotImplementedError as e: raise HTTPException(501, str(e))
    commit(s); return order_out(o)

@app.get("/investor/summary")
def inv_summary(u=Depends(user_dep("investor")), s=Depends(get_db)):
    return json.loads(json.dumps(ledger.investor_summary(s, u.id), default=str))

@app.get("/investor/investments")
def inv_investments(u=Depends(user_dep("investor")), s=Depends(get_db)):
    out = []
    for a in s.query(Allocation).filter(Allocation.investor_id == u.id):  # privacy: business name + purpose only, no documents
        app_ = s.get(Application, a.application_id); sme = s.get(Sme, app_.sme_id); loan = s.query(Loan).filter(Loan.application_id == app_.id).first()
        d = s.query(Distribution).filter(Distribution.investor_id == u.id, Distribution.loan_id == loan.id).all()
        out.append({"business": sme.business_name, "industry": app_.industry, "purpose": app_.purpose, "allocated": str(a.amount),
                    "outstanding": str(a.outstanding), "loan_status": loan.status, "rate_pct": str(loan.rate_pct),
                    "principal_returned": str(sum((x.principal for x in d), Decimal(0))), "interest_earned": str(sum((x.interest for x in d), Decimal(0)))})
    return out

def _date(x): return dt.date.fromisoformat(x) if x else None
@app.get("/investor/statement")
def inv_statement(start: Optional[str] = None, end: Optional[str] = None, u=Depends(user_dep("investor")), s=Depends(get_db)):
    return ledger.investor_statement(s, u.id, _date(start), _date(end))

# ---------- SME ----------
class Profile(BaseModel):
    business_name: str; reg_number: Optional[str] = None; industry: str; description: str = ""; country: str = ""
    location: str = ""; established: str = ""; employees: int = 0
    monthly_revenue: Decimal = Decimal(0); monthly_expenses: Decimal = Decimal(0); monthly_debt: Decimal = Decimal(0); contact: str = ""

def my_sme(s, u): return s.query(Sme).filter(Sme.user_id == u.id).first()

@app.put("/sme/profile")
def put_profile(b: Profile, u=Depends(user_dep("sme")), s=Depends(get_db)):
    if b.industry not in INDUSTRIES: raise HTTPException(400, "Unknown industry")
    m = my_sme(s, u) or Sme(user_id=u.id)
    for k, v in b.model_dump().items(): setattr(m, k, v)
    s.add(m); commit(s); return row(m)

@app.get("/sme/profile")
def get_profile(u=Depends(user_dep("sme")), s=Depends(get_db)):
    m = my_sme(s, u); return row(m) if m else None

@app.post("/sme/documents")
def upload(kind: str = Form(...), file: UploadFile = File(...), u=Depends(user_dep("sme")), s=Depends(get_db)):
    m = my_sme(s, u)
    if not m: raise HTTPException(400, "Complete your business profile first")
    data = file.file.read()
    if file.content_type not in ALLOWED: raise HTTPException(400, "Only PDF, PNG, JPEG or CSV files are accepted")
    if len(data) > 10_000_000: raise HTTPException(400, "File must be under 10 MB")
    path = storage.save(data, file.content_type)
    d = Document(sme_id=m.id, kind=kind, filename=os.path.basename(file.filename or "file"), path=path, mime=file.content_type)
    s.add(d); commit(s); return row(d, "path")

@app.get("/sme/documents")
def docs(u=Depends(user_dep("sme")), s=Depends(get_db)):
    m = my_sme(s, u); return [row(d, "path") for d in s.query(Document).filter(Document.sme_id == m.id)] if m else []

@app.get("/documents/{did}")
def doc_download(did: str, u=Depends(user_dep("sme", "admin")), s=Depends(get_db)):
    d = s.get(Document, did)
    if not d or (u.role == "sme" and d.sme_id != (my_sme(s, u).id if my_sme(s, u) else None)): raise HTTPException(404, "Not found")
    return Response(storage.read(d.path), media_type=d.mime, headers={"Content-Disposition": f'inline; filename="{d.filename}"'})

class NewApp(BaseModel): amount: Decimal; purpose: str; use_of_funds: str = ""; months: int; comments: str = ""
class Confirm(BaseModel): monthly_revenue: Decimal; monthly_expenses: Decimal; monthly_debt: Decimal = Decimal(0)

def build_assessment(s, m, a, res, err):
    res = res or ai.Assessment(summary="Automatic document analysis could not be completed. The figures below come from the applicant's own profile and are unverified.",
                               missing_information=["Bank statement figures could not be extracted"])
    rev = D(res.est_monthly_revenue) or m.monthly_revenue; exp = D(res.est_monthly_expenses) or m.monthly_expenses; debt = D(res.existing_debt_payments) or m.monthly_debt
    inc = list(res.inconsistencies)
    if not err and m.monthly_revenue and rev and abs(rev - m.monthly_revenue) > m.monthly_revenue * Decimal("0.2"):
        inc.append(f"Declared monthly revenue R{m.monthly_revenue} differs by more than 20% from the statements (R{rev})")
    aff = ledger.affordability(rev, exp, debt, a.amount, ledger.cfg(s, "rate_pct"), a.months, missing=bool(err))
    data = res.model_dump(); data["inconsistencies"] = inc
    return {"ai": data, "source": "unavailable" if err else "gemini", "error": err, "affordability": aff,
            "extracted": {"monthly_revenue": str(q(rev)), "monthly_expenses": str(q(exp)), "monthly_debt": str(q(debt))},
            "disclaimer": "Preliminary AI-generated feedback, not a funding decision. Risk categories support a human decision and do not predict repayment."}

def run_analysis(s, m, a):
    docs = s.query(Document).filter(Document.sme_id == m.id).all()
    if not docs: raise HTTPException(400, "Upload at least one bank statement before applying")
    res = err = None
    try: res = ai.analyze({k: v for k, v in row(m).items() if k not in ("id", "user_id")}, [(d.mime, storage.read(d.path), d.filename) for d in docs])
    except ai.AIError as e: err = str(e)
    a.assessment = json.dumps(build_assessment(s, m, a, res, err))

@app.post("/sme/applications")
def create_app(b: NewApp, u=Depends(user_dep("sme")), s=Depends(get_db)):
    m = my_sme(s, u)
    if not m: raise HTTPException(400, "Complete your business profile first")
    if b.amount <= 0 or not (1 <= b.months <= int(ledger.cfg(s, "max_months"))): raise HTTPException(400, "Invalid amount or duration")
    a = Application(sme_id=m.id, industry=m.industry, amount=b.amount, purpose=b.purpose, use_of_funds=b.use_of_funds, months=b.months, comments=b.comments)
    s.add(a); s.flush(); run_analysis(s, m, a); commit(s)
    return {**row(a), "assessment": json.loads(a.assessment)}

@app.post("/sme/applications/{aid}/reanalyze")
def reanalyze(aid: str, u=Depends(user_dep("sme")), s=Depends(get_db)):
    m = my_sme(s, u); a = s.get(Application, aid)
    if not a or a.sme_id != m.id or a.status != "draft": raise HTTPException(400, "Application cannot be re-analysed")
    run_analysis(s, m, a); commit(s); return {**row(a), "assessment": json.loads(a.assessment)}

@app.post("/sme/applications/{aid}/submit")
def submit_app(aid: str, b: Confirm, u=Depends(user_dep("sme")), s=Depends(get_db)):
    m = my_sme(s, u); a = s.get(Application, aid)
    if not a or a.sme_id != m.id or a.status not in ("draft", "info_requested"): raise HTTPException(400, "Application cannot be submitted")
    m.monthly_revenue, m.monthly_expenses, m.monthly_debt = b.monthly_revenue, b.monthly_expenses, b.monthly_debt  # applicant-confirmed values
    old = json.loads(a.assessment); old["affordability"] = ledger.affordability(b.monthly_revenue, b.monthly_expenses, b.monthly_debt, a.amount, ledger.cfg(s, "rate_pct"), a.months)
    a.assessment = json.dumps(old); a.status = "submitted"; ledger.audit(s, u.id, "submit", {"application": a.id}); commit(s)
    return {**row(a), "assessment": old}

@app.get("/sme/applications")
def my_apps(u=Depends(user_dep("sme")), s=Depends(get_db)):
    m = my_sme(s, u); return [{**row(a), "assessment": json.loads(a.assessment or "null")} for a in s.query(Application).filter(Application.sme_id == m.id).order_by(Application.created.desc())] if m else []

@app.get("/sme/loans")
def my_loans(u=Depends(user_dep("sme")), s=Depends(get_db)):
    m = my_sme(s, u); out = []
    for l in (s.query(Loan).filter(Loan.sme_id == m.id) if m else []):
        out.append({**row(l), "schedule": [row(i) for i in s.query(Instalment).filter(Instalment.loan_id == l.id).order_by(Instalment.n)],
                    "repayments": [row(r) for r in s.query(Repayment).filter(Repayment.loan_id == l.id).order_by(Repayment.created)],
                    "awaiting_disbursement": l.status == "pending_disbursement"})
    return out

class Repay(BaseModel): loan_id: str; amount: Decimal
@app.post("/sme/repay")
def repay(b: Repay, u=Depends(user_dep("sme")), s=Depends(get_db)):
    m = my_sme(s, u); l = s.get(Loan, b.loan_id)
    if not l or l.sme_id != m.id: raise HTTPException(404, "Loan not found")
    if l.status != "active": raise HTTPException(400, "Repayments open once your financing has been paid out")
    if b.amount <= 0 or b.amount > l.total_due - l.repaid: raise HTTPException(400, f"Amount must be between 0.01 and {l.total_due - l.repaid}")
    try: o = payments.create_order(s, "repayment", u.id, b.amount, loan_id=l.id)
    except NotImplementedError as e: raise HTTPException(501, str(e))
    commit(s); return order_out(o)

@app.get("/sme/statement")
def sme_stmt(start: Optional[str] = None, end: Optional[str] = None, u=Depends(user_dep("sme")), s=Depends(get_db)):
    m = my_sme(s, u)
    if not m: raise HTTPException(400, "Complete your business profile first")
    return ledger.sme_statement(s, m, _date(start), _date(end))

# ---------- admin ----------
admin = user_dep("admin")

@app.get("/admin/overview")
def overview(u=Depends(admin), s=Depends(get_db)):
    loans = s.query(Loan).all(); cs = s.query(Contribution).all(); sm = lambda xs: str(sum(xs, Decimal(0)))
    cnt = lambda st: s.query(Application).filter(Application.status == st).count()
    return {"total_contributed": sm([c.amount for c in cs]), "available": sm([c.amount - c.allocated for c in cs]),
            "allocated": sm([c.allocated for c in cs]), "approved_financing": sm([l.principal for l in loans]),
            "outstanding_principal": sm([l.principal_outstanding for l in loans]), "repayments_received": sm([l.repaid for l in loans]),
            "investors": s.query(User).filter(User.role == "investor").count(), "smes": s.query(Sme).count(),
            "pending": cnt("submitted"), "approved": cnt("approved"), "rejected": cnt("rejected"),
            "pools": json.loads(json.dumps([ledger.pool(s, i) for i in INDUSTRIES], default=str))}

@app.get("/admin/investors")
def investors(u=Depends(admin), s=Depends(get_db)):
    return json.loads(json.dumps([{"name": i.name, "email": i.email, **{k: v for k, v in ledger.investor_summary(s, i.id).items() if k in ("total_contributed", "available", "allocated", "principal_returned", "interest_earned")}}
                                  for i in s.query(User).filter(User.role == "investor")], default=str))

@app.get("/admin/applications")
def all_apps(status: Optional[str] = None, u=Depends(admin), s=Depends(get_db)):
    qy = s.query(Application).filter(Application.status != "draft")
    if status: qy = qy.filter(Application.status == status)
    return [{**row(a, "assessment"), "business": s.get(Sme, a.sme_id).business_name,
             "risk": (json.loads(a.assessment or "{}").get("affordability") or {}).get("risk_category")} for a in qy.order_by(Application.created.desc())]

@app.get("/admin/applications/{aid}")
def app_detail(aid: str, u=Depends(admin), s=Depends(get_db)):
    a = s.get(Application, aid)
    if not a: raise HTTPException(404, "Not found")
    plan, avail = ledger.preview_allocation(s, a.industry, a.amount)
    rate = ledger.cfg(s, "rate_pct"); interest, total = ledger.terms(a.amount, rate, a.months)
    return {**row(a, "assessment"), "assessment": json.loads(a.assessment or "null"), "sme": row(s.get(Sme, a.sme_id)),
            "documents": [row(d, "path") for d in s.query(Document).filter(Document.sme_id == a.sme_id)],
            "pool_available": str(avail), "can_fund": plan is not None,
            "allocation_preview": [{"investor": s.get(User, c.investor_id).name, "amount": str(sh)} for c, sh in (plan or [])],
            "terms": {"rate_pct": str(rate), "interest": str(interest), "total_due": str(total), "monthly": str(q(total / a.months))}}

class Decision(BaseModel): action: str; amount: Optional[Decimal] = None; notes: str = ""
@app.post("/admin/applications/{aid}/decision")
def decide(aid: str, b: Decision, u=Depends(admin), s=Depends(get_db)):
    a = s.get(Application, aid)
    if not a or a.status not in ("submitted", "info_requested"): raise HTTPException(400, "Application is not awaiting a decision")
    try:
        if b.action == "approve": ledger.approve(s, a, b.amount or a.amount, b.notes, u.id)
        elif b.action in ("reject", "request_info"):
            if b.action == "reject" and not b.notes.strip(): raise ValueError("A rejection reason is required")
            a.status = "rejected" if b.action == "reject" else "info_requested"; a.decision_notes, a.decided_by = b.notes, u.id
            ledger.audit(s, u.id, b.action, {"application": a.id, "notes": b.notes})
        else: raise ValueError("Unknown action")
        commit(s)
    except ValueError as e: s.rollback(); raise HTTPException(400, str(e))
    return {"status": a.status}

@app.get("/admin/loans")
def admin_loans(u=Depends(admin), s=Depends(get_db)):
    return [{**row(l), "business": s.get(Sme, l.sme_id).business_name} for l in s.query(Loan)]

@app.get("/admin/chain")
def chain_list(u=Depends(admin), s=Depends(get_db)):
    return [{**row(c), "explorer": chain.EXPLORER + c.tx_hash if c.tx_hash else None, "network": "Avalanche Fuji TESTNET"} for c in s.query(ChainTx).order_by(ChainTx.created.desc())]

@app.post("/admin/chain/reconcile")
def chain_reconcile(u=Depends(admin), s=Depends(get_db)): return {"updated": chain.reconcile(s)}

@app.get("/admin/audit")
def audit_list(u=Depends(admin), s=Depends(get_db)): return [row(a) for a in s.query(Audit).order_by(Audit.created.desc()).limit(200)]

@app.get("/admin/settings")
def get_settings(u=Depends(admin), s=Depends(get_db)): return {x.key: x.value for x in s.query(Setting)}

@app.put("/admin/settings")
def put_settings(b: dict, u=Depends(admin), s=Depends(get_db)):
    for k, v in b.items():
        if k in DEFAULT_SETTINGS and s.get(Setting, k): s.get(Setting, k).value = str(D(v) if k != "allocation_policy" else v)
    ledger.audit(s, u.id, "settings", b); commit(s); return {x.key: x.value for x in s.query(Setting)}

class Disburse(BaseModel): reference: str
@app.post("/admin/loans/{lid}/disburse")
def disburse(lid: str, b: Disburse, u=Depends(admin), s=Depends(get_db)):
    l = s.get(Loan, lid)
    if not l: raise HTTPException(404, "Not found")
    try: ledger.disburse(s, l, b.reference, u.id); commit(s)
    except ValueError as e: s.rollback(); raise HTTPException(400, str(e))
    return {"status": l.status}
