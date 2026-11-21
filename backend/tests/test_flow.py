import os, tempfile, json
os.environ.setdefault("DATABASE_URL", f"sqlite:///{tempfile.mkdtemp()}/t.db"); os.environ["UPLOAD_DIR"] = tempfile.mkdtemp()
from decimal import Decimal
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from app.main import app
from app import ledger
c = TestClient(app)

def reg(role, i):
    r = c.post("/auth/register", json={"email": f"{role}{i}@t.io", "password": "password1", "name": f"{role}{i}", "role": role}).json()
    return {"Authorization": "Bearer " + r["token"]}

def pay(h, o, **kw): return c.post(f"/payments/{o['ref']}/pay", json={"method": "eft", "bank": "FNB", **kw}, headers=h).json()
CSV = b"date,description,debit,credit\n2026-01-03,Customer EFT,0,50000\n"

def test_pro_rata_sums_exactly():
    assert sum(ledger.pro_rata(Decimal("1000.01"), [1, 1, 1])) == Decimal("1000.01")

def test_full_lifecycle():
    inv1, inv2, sme = reg("investor", 1), reg("investor", 2), reg("sme", 1)
    assert c.post("/auth/register", json={"email": "x@t.io", "password": "password1", "name": "x", "role": "admin"}).status_code == 400
    from app.main import SessionLocal, User, hash_pw
    with SessionLocal() as s: s.add(User(email="a@t.io", name="a", pw=hash_pw("password1"), role="admin")); s.commit()
    ad = {"Authorization": "Bearer " + c.post("/auth/login", json={"email": "a@t.io", "password": "password1"}).json()["token"]}
    for h, amt in [(inv1, "1000"), (inv2, "2000")]:
        o = c.post("/investor/contribute", json={"industry": "Agriculture", "amount": amt}, headers=h).json()
        assert o["checkout"]["type"] == "internal" and c.get(f"/payments/{o['ref']}", headers=h).json()["description"].startswith("Contribution")
        assert pay(h, o)["result"] == "paid"
        assert pay(h, o)["result"] != "paid"  # replay cannot double-credit
        assert c.get(f"/payments/{o['ref']}", headers=inv2 if h is inv1 else inv1).status_code == 404  # not your order
    o = c.post("/investor/contribute", json={"industry": "Agriculture", "amount": "50"}, headers=inv1).json()
    assert c.post(f"/payments/{o['ref']}/pay", json={"method": "eft"}, headers=inv1).status_code == 400  # bank required
    assert pay(inv1, o, outcome="CANCELLED")["order"]["status"] == "cancelled"
    assert c.get("/investor/summary", headers=inv1).json()["available"] == "1000.00"
    assert c.get("/admin/overview", headers=inv1).status_code == 403
    c.put("/sme/profile", json={"business_name": "Farm Co", "industry": "Agriculture", "monthly_revenue": "10000", "monthly_expenses": "6000"}, headers=sme)
    assert c.post("/sme/applications", json={"amount": "1500", "purpose": "Irrigation", "months": 6}, headers=sme).status_code == 400  # needs a document
    c.post("/sme/documents", data={"kind": "Bank statement"}, files={"file": ("s.csv", CSV, "text/csv")}, headers=sme)
    a = c.post("/sme/applications", json={"amount": "1500", "purpose": "Irrigation", "months": 6}, headers=sme).json()
    assert a["assessment"]["source"] == "unavailable" and "GEMINI_API_KEY" in a["assessment"]["error"]  # clear reason, not a silent fallback
    c.post(f"/sme/applications/{a['id']}/submit", json={"monthly_revenue": "10000", "monthly_expenses": "6000"}, headers=sme)
    d = c.get(f"/admin/applications/{a['id']}", headers=ad).json()
    assert d["can_fund"] and sum(Decimal(x["amount"]) for x in d["allocation_preview"]) == Decimal("1500.00")
    assert c.post(f"/admin/applications/{a['id']}/decision", json={"action": "approve", "amount": "99999"}, headers=ad).status_code == 400
    assert c.post(f"/admin/applications/{a['id']}/decision", json={"action": "approve", "amount": "1500"}, headers=ad).status_code == 200
    assert c.post(f"/admin/applications/{a['id']}/decision", json={"action": "approve", "amount": "1500"}, headers=ad).status_code == 400
    assert c.get("/investor/summary", headers=inv1).json()["allocated"] == "500.00"
    loan = c.get("/sme/loans", headers=sme).json()[0]; total = Decimal(loan["total_due"])
    assert loan["status"] == "pending_disbursement" and loan["schedule"] == []
    assert c.post("/sme/repay", json={"loan_id": loan["id"], "amount": "10"}, headers=sme).status_code == 400  # not paid out yet
    assert c.post(f"/admin/loans/{loan['id']}/disburse", json={"reference": " "}, headers=ad).status_code == 400
    assert c.post(f"/admin/loans/{loan['id']}/disburse", json={"reference": "EFT-0001"}, headers=ad).status_code == 200
    assert c.post(f"/admin/loans/{loan['id']}/disburse", json={"reference": "EFT-0002"}, headers=ad).status_code == 400
    loan = c.get("/sme/loans", headers=sme).json()[0]; assert loan["status"] == "active" and len(loan["schedule"]) == 6
    o = c.post("/sme/repay", json={"loan_id": loan["id"], "amount": str(total)}, headers=sme).json()
    assert pay(sme, o)["result"] == "paid"
    loan = c.get("/sme/loans", headers=sme).json()[0]
    assert loan["status"] == "repaid" and Decimal(loan["principal_outstanding"]) == 0
    s1, s2 = c.get("/investor/summary", headers=inv1).json(), c.get("/investor/summary", headers=inv2).json()
    assert s1["allocated"] == "0.00" and s1["principal_returned"] == "500.00" and s2["principal_returned"] == "1000.00"
    interest = Decimal(loan["interest"]); got = Decimal(s1["interest_earned"]) + Decimal(s2["interest_earned"])
    assert got == interest - ledger.q(interest * Decimal("0.10"))
    st = c.get("/investor/statement", headers=inv1).json()
    assert {r["type"] for r in st["rows"]} == {"Contribution", "Principal returned", "Interest earned"}
    assert c.get("/investor/statement?start=2099-01-01", headers=inv1).json()["rows"] == []  # date filter
    ss = c.get("/sme/statement", headers=sme).json()
    assert [r["type"] for r in ss["rows"]] == ["Financing received", "Repayment"] and ss["summary"][-1]["value"] == "0.00"
    assert any(x["event"] == "recordDisbursement" for x in c.get("/admin/chain", headers=ad).json())

def test_gemini_extraction_pipeline(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    months = [{"month": f"2026-{m:02d}", "deposits": 100000 + (m % 3) * 5000, "withdrawals": 70000} for m in range(1, 9)]
    body = {"candidates": [{"content": {"parts": [{"text": "```json\n" + json.dumps({"summary": "Steady.", "monthly": months, "existing_debt_payments": 4850, "risks": [], "confidence": "medium"}) + "\n```"}]}}]}
    resp = MagicMock(status_code=200, content=b"1"); resp.json.return_value = body
    from app import ai
    with patch("app.ai.httpx.post", lambda *a, **k: resp):
        r = ai.analyze({"business_name": "X"}, [("application/pdf", b"%PDF", "s.pdf")])
    assert r.months_covered == 8 and r.avg_monthly_deposits == 105625.0 and r.est_monthly_expenses == 65150.0
    assert any("Only 8 of the last 12" in x for x in r.missing_information) and r.revenue_consistency.startswith("Consistent")
    bad = MagicMock(status_code=400, content=b"1"); bad.json.return_value = {"error": {"message": "API key not valid"}}
    with patch("app.ai.httpx.post", lambda *a, **k: bad):
        try: ai.analyze({}, [("application/pdf", b"x", "s.pdf")]); assert False
        except ai.AIError as e: assert "API key not valid" in str(e)
