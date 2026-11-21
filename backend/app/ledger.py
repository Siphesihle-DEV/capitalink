"""All authoritative money logic. Decimal only; no floats."""
import datetime as dt, json
from decimal import Decimal, ROUND_HALF_UP
from sqlalchemy import func
from .db import *
from . import chain

CENT = Decimal("0.01")
D = lambda x: Decimal(str(x or 0))
q = lambda x: D(x).quantize(CENT, ROUND_HALF_UP)

def cfg(s, key): return D(s.get(Setting, key).value)

def pro_rata(total, weights):
    """Largest-remainder split in whole cents; shares always sum exactly to total."""
    t = int(q(total) * 100); w = [D(x) for x in weights]; tw = sum(w)
    if tw <= 0: raise ValueError("no weights")
    raw = [Decimal(t) * x / tw for x in w]
    base = [int(r) for r in raw]
    left = t - sum(base)
    for i in sorted(range(len(w)), key=lambda i: raw[i] - base[i], reverse=True)[:left]: base[i] += 1
    return [Decimal(b) / 100 for b in base]

def terms(principal, rate_pct, months):
    interest = q(D(principal) * D(rate_pct) / 100 * months / 12)
    return interest, q(D(principal) + interest)

def schedule(total, months, start=None):
    start = start or dt.date.today()
    amts = pro_rata(total, [1] * months)
    return [(i + 1, start + dt.timedelta(days=30 * (i + 1)), a) for i, a in enumerate(amts)]

def affordability(revenue, expenses, debt, principal, rate_pct, months, missing=False):
    """Monthly FCF = revenue - expenses - existing debt. DSCR = FCF / proposed monthly instalment."""
    fcf = q(D(revenue) - D(expenses) - D(debt))
    _, total = terms(principal, rate_pct, months)
    inst = q(total / months) if months else Decimal(0)
    dscr = (fcf / inst).quantize(Decimal("0.01")) if inst > 0 else None
    if missing or D(revenue) <= 0: cat = "Insufficient Information"
    elif dscr >= Decimal("1.5"): cat = "Low Risk"
    elif dscr >= Decimal("1.0"): cat = "Moderate Risk"
    else: cat = "High Risk"
    return {"monthly_free_cash_flow": str(fcf), "proposed_monthly_instalment": str(inst), "dscr": str(dscr),
            "risk_category": cat, "assumptions": f"Flat interest {rate_pct}% p.a. on principal over {months} months; "
            "inputs are applicant-confirmed figures, not verified facts. Decision-support only."}

def pool(s, industry):
    rows = s.query(Contribution).filter(Contribution.industry == industry).all()
    tot = sum((c.amount for c in rows), Decimal(0)); alloc = sum((c.allocated for c in rows), Decimal(0))
    return {"industry": industry, "contributed": tot, "allocated": alloc, "available": tot - alloc}

def preview_allocation(s, industry, amount, lock=False):
    qy = s.query(Contribution).filter(Contribution.industry == industry).order_by(Contribution.created, Contribution.id)
    if lock: qy = qy.with_for_update()  # serialise concurrent approvals on Postgres
    cs = [c for c in qy if c.amount - c.allocated > 0]
    avail = sum((c.amount - c.allocated for c in cs), Decimal(0))
    if q(amount) > avail: return None, avail
    return list(zip(cs, pro_rata(amount, [c.amount - c.allocated for c in cs]))), avail

def audit(s, actor, action, detail): s.add(Audit(actor=actor, action=action, detail=json.dumps(detail, default=str)))

def approve(s, app, amount, notes, admin_id):
    if app.status not in ("submitted",): raise ValueError(f"Application is {app.status}, not submitted")
    amount = q(amount)
    plan, avail = preview_allocation(s, app.industry, amount, lock=True)
    if plan is None: raise ValueError(f"Only {avail} available in {app.industry} pool; cannot allocate {amount}")
    rate = cfg(s, "rate_pct"); interest, total = terms(amount, rate, app.months)
    loan = Loan(application_id=app.id, sme_id=app.sme_id, principal=amount, rate_pct=rate, months=app.months,
                interest=interest, total_due=total, principal_outstanding=amount, status="pending_disbursement")
    s.add(loan); s.flush()
    for c, share in plan:
        c.allocated += share
        s.add(Allocation(application_id=app.id, contribution_id=c.id, investor_id=c.investor_id, amount=share, outstanding=share))
    app.status, app.approved_amount, app.decision_notes, app.decided_by = "approved", amount, notes, admin_id
    audit(s, admin_id, "approve", {"application": app.id, "amount": amount, "allocations": [(c.id, sh) for c, sh in plan]})
    fid = chain.h(loan.id)
    chain.record(s, "registerFinancing", loan.id, fid, chain.cents(amount), chain.h(app.id))
    chain.record(s, "recordAllocation", f"alloc:{loan.id}", fid, chain.cents(amount), chain.h(f"alloc:{loan.id}"))
    return loan

def disburse(s, loan, reference, admin_id):
    """Admin confirms the bank (EFT) payment to the SME. Only now does financing become active and the schedule start."""
    if loan.status != "pending_disbursement": raise ValueError("Financing is not awaiting disbursement")
    if not (reference or "").strip(): raise ValueError("Enter the bank payment reference")
    loan.status, loan.disbursed_at, loan.disbursement_ref = "active", now(), reference.strip()
    for n, due, a in schedule(loan.total_due, loan.months): s.add(Instalment(loan_id=loan.id, n=n, due=due, amount=a))
    audit(s, admin_id, "disburse", {"loan": loan.id, "amount": loan.principal, "reference": loan.disbursement_ref})
    chain.record(s, "recordDisbursement", f"disb:{loan.id}", chain.h(loan.id), chain.cents(loan.principal), chain.h(f"disb:{loan.disbursement_ref}"))

def apply_repayment(s, loan, amount, ref):
    if loan.status != "active": raise ValueError("Repayments open once the financing has been disbursed")
    amount = q(amount); remaining = loan.total_due - loan.repaid
    if amount <= 0 or amount > remaining: raise ValueError(f"Repayment must be between 0.01 and {remaining}")
    if amount == remaining: p = loan.principal_outstanding
    else: p = min(q(amount * loan.principal / loan.total_due), loan.principal_outstanding)
    gross_int = amount - p; fee = q(gross_int * cfg(s, "platform_fee_pct") / 100); net_int = gross_int - fee
    rp = Repayment(loan_id=loan.id, amount=amount, principal_part=p, interest_part=gross_int, fee=fee, ref=ref)
    s.add(rp); s.flush()
    allocs = s.query(Allocation).filter(Allocation.application_id == loan.application_id).order_by(Allocation.id).all()
    pw = [a.outstanding for a in allocs]; iw = [a.amount for a in allocs]
    pshare = pro_rata(p, pw) if sum(pw) > 0 else [Decimal(0)] * len(allocs)
    ishare = pro_rata(net_int, iw); fshare = pro_rata(fee, iw)
    for a, ps, i_s, fs in zip(allocs, pshare, ishare, fshare):
        a.outstanding -= ps
        c = s.get(Contribution, a.contribution_id); c.allocated -= ps  # returned principal becomes available again
        s.add(Distribution(repayment_id=rp.id, loan_id=loan.id, investor_id=a.investor_id, contribution_id=c.id,
                           principal=ps, interest=i_s, fee=fs))
    left = amount
    for ins in s.query(Instalment).filter(Instalment.loan_id == loan.id).order_by(Instalment.n):
        if left <= 0: break
        pay = min(left, ins.amount - ins.paid); ins.paid += pay; left -= pay
    loan.repaid += amount; loan.principal_outstanding -= p
    if loan.repaid >= loan.total_due: loan.status = "repaid"
    fid = chain.h(loan.id)
    chain.record(s, "recordRepayment", ref, fid, chain.cents(amount), chain.cents(p), chain.cents(gross_int), chain.h(ref))
    chain.record(s, "recordDistribution", f"dist:{ref}", fid, chain.cents(p + net_int), chain.h(f"dist:{ref}"))
    audit(s, "system", "repayment", {"loan": loan.id, "amount": amount, "principal": p, "interest": gross_int, "fee": fee})
    return rp

def investor_summary(s, uid_):
    cs = s.query(Contribution).filter(Contribution.investor_id == uid_).all()
    tot = sum((c.amount for c in cs), Decimal(0)); alloc = sum((c.allocated for c in cs), Decimal(0))
    ds = s.query(Distribution).filter(Distribution.investor_id == uid_).all()
    by = {}
    for c in cs: by[c.industry] = by.get(c.industry, Decimal(0)) + c.amount
    return {"total_contributed": tot, "available": tot - alloc, "allocated": alloc, "outstanding_financing": alloc,
            "principal_returned": sum((d.principal for d in ds), Decimal(0)),
            "interest_earned": sum((d.interest for d in ds), Decimal(0)),
            "by_industry": [{"industry": k, "amount": v} for k, v in by.items()],
            "note": "Projected figures are not guaranteed returns."}

def _d(x): return x.date() if hasattr(x, "date") else x
def _in(x, start, end): x = _d(x); return (not start or x >= start) and (not end or x <= end)
def _out(rows): return [{**r, "date": str(r["date"])[:10], "amount": str(r["amount"])} for r in sorted(rows, key=lambda r: r["date"])]

def investor_statement(s, uid_, start=None, end=None):
    rows = []
    for c in s.query(Contribution).filter(Contribution.investor_id == uid_):
        if _in(c.created, start, end): rows.append({"date": c.created, "type": "Contribution", "description": f"{c.industry} pool", "reference": c.ref or c.id[:8], "amount": c.amount, "detail": ""})
    tot = {"p": Decimal(0), "i": Decimal(0), "f": Decimal(0)}
    for d in s.query(Distribution).filter(Distribution.investor_id == uid_):
        rp = s.get(Repayment, d.repayment_id)
        if not _in(rp.created, start, end): continue
        biz = s.get(Sme, s.get(Loan, d.loan_id).sme_id).business_name
        if d.principal: rows.append({"date": rp.created, "type": "Principal returned", "description": biz, "reference": rp.ref, "amount": d.principal, "detail": ""})
        if d.interest: rows.append({"date": rp.created, "type": "Interest earned", "description": biz, "reference": rp.ref, "amount": d.interest, "detail": f"net of fee {d.fee}"})
        tot["p"] += d.principal; tot["i"] += d.interest; tot["f"] += d.fee
    contributed = sum((r["amount"] for r in rows if r["type"] == "Contribution"), Decimal(0))
    return {"rows": _out(rows), "summary": [{"label": "Contributed", "value": str(contributed)}, {"label": "Principal returned", "value": str(tot["p"])},
            {"label": "Interest earned (net)", "value": str(tot["i"])}, {"label": "Platform fees deducted", "value": str(tot["f"])}]}

def sme_statement(s, sme, start=None, end=None):
    rows = []; paid = prin = intr = recv = Decimal(0); owing = Decimal(0)
    for l in s.query(Loan).filter(Loan.sme_id == sme.id):
        if l.disbursed_at and _in(l.disbursed_at, start, end):
            rows.append({"date": l.disbursed_at, "type": "Financing received", "description": f"Financing of {l.principal} at {l.rate_pct}% p.a.", "reference": l.disbursement_ref, "amount": l.principal, "detail": ""}); recv += l.principal
        for r in s.query(Repayment).filter(Repayment.loan_id == l.id):
            if _in(r.created, start, end):
                rows.append({"date": r.created, "type": "Repayment", "description": "Loan repayment", "reference": r.ref, "amount": r.amount, "detail": f"principal {r.principal_part}, interest {r.interest_part}"})
                paid += r.amount; prin += r.principal_part; intr += r.interest_part
        owing += l.total_due - l.repaid
    return {"rows": _out(rows), "summary": [{"label": "Financing received", "value": str(recv)}, {"label": "Total repaid", "value": str(paid)},
            {"label": "Principal repaid", "value": str(prin)}, {"label": "Interest paid", "value": str(intr)}, {"label": "Total still owing (all time)", "value": str(owing)}]}
