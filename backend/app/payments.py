"""Payment providers (ZAR). PAYMENT_PROVIDER=sandbox uses the built-in checkout; payfast redirects to PayFast (sandbox or live).
All providers end in process_event(): verified, idempotent, amount-checked. A browser redirect is never proof of payment."""
import os, hmac, hashlib, json, uuid, urllib.parse as up, httpx
from sqlalchemy.exc import IntegrityError
from .db import PaymentOrder, WebhookEvent, Contribution, Loan
from . import ledger

PROVIDER = lambda: os.getenv("PAYMENT_PROVIDER", "sandbox")  # sandbox | payfast
PF_SANDBOX = lambda: os.getenv("PAYFAST_SANDBOX", "1") == "1"
PF_HOST = lambda: "https://sandbox.payfast.co.za" if PF_SANDBOX() else "https://www.payfast.co.za"
SECRET = lambda: os.getenv("WEBHOOK_SECRET", "dev-webhook-secret").encode()
def environment(): return "live" if PROVIDER() == "payfast" and not PF_SANDBOX() else "sandbox"
def sign(raw: bytes) -> str: return hmac.new(SECRET(), raw, hashlib.sha256).hexdigest()

def describe(o): return f"Contribution to the {o.industry} pool" if o.kind == "contribution" else "Loan repayment"

def create_order(s, kind, user_id, amount, industry=None, loan_id=None):
    o = PaymentOrder(ref=f"CL-{uuid.uuid4().hex[:10].upper()}", kind=kind, user_id=user_id, amount=ledger.q(amount), industry=industry, loan_id=loan_id, provider=PROVIDER())
    s.add(o); s.flush(); return o

def pf_signature(pairs, passphrase=""):
    qs = "&".join(f"{k}={up.quote_plus(str(v).strip())}" for k, v in pairs if v not in ("", None))
    if passphrase: qs += f"&passphrase={up.quote_plus(passphrase.strip())}"
    return hashlib.md5(qs.encode()).hexdigest()

def checkout_info(o):
    if o.provider != "payfast": return {"type": "internal", "url": f"/pay/{o.ref}"}
    front, api = os.getenv("FRONTEND_URL", "http://localhost:5173"), os.getenv("API_PUBLIC_URL", "http://localhost:8000")
    pairs = [("merchant_id", os.getenv("PAYFAST_MERCHANT_ID", "10000100")), ("merchant_key", os.getenv("PAYFAST_MERCHANT_KEY", "46f0cd694581a")),
             ("return_url", f"{front}/pay/{o.ref}/return"), ("cancel_url", f"{front}/pay/{o.ref}/return"), ("notify_url", f"{api}/payments/webhook/payfast"),
             ("m_payment_id", o.ref), ("amount", f"{o.amount:.2f}"), ("item_name", describe(o))]
    return {"type": "form", "action": PF_HOST() + "/eng/process", "fields": dict(pairs + [("signature", pf_signature(pairs, os.getenv("PAYFAST_PASSPHRASE", "")))])}

def process_event(s, event_id, ref, status, amount):
    if status not in ("PAID", "FAILED", "CANCELLED"): return "ignored"
    if s.get(WebhookEvent, event_id): return "duplicate"
    s.add(WebhookEvent(event_id=event_id, payload=json.dumps({"ref": ref, "status": status, "amount": str(amount)})))
    try: s.flush()
    except IntegrityError: s.rollback(); return "duplicate"
    o = s.query(PaymentOrder).filter(PaymentOrder.ref == ref).first()
    if not o: raise LookupError("Unknown order")
    if o.status != "pending": return f"already {o.status}"
    if status != "PAID": o.status = status.lower(); return o.status
    if ledger.q(amount) != o.amount: o.status = "mismatch"; return "amount mismatch"
    if o.kind == "contribution": s.add(Contribution(investor_id=o.user_id, industry=o.industry, amount=o.amount, ref=o.ref))
    else: ledger.apply_repayment(s, s.get(Loan, o.loan_id, with_for_update=True), o.amount, o.ref)
    o.status = "paid"; return "paid"

def handle_event(s, raw: bytes, signature: str):
    if not hmac.compare_digest(sign(raw), signature or ""): raise PermissionError("Invalid signature")
    ev = json.loads(raw); return process_event(s, ev["event_id"], ev["ref"], ev["status"], ev["amount"])

def sandbox_pay(s, order, outcome="PAID"):
    raw = json.dumps({"event_id": f"{order.ref}:{outcome}", "ref": order.ref, "status": outcome, "amount": str(order.amount)}).encode()
    return handle_event(s, raw, sign(raw))

def payfast_itn(s, raw: bytes):
    pairs = up.parse_qsl(raw.decode(), keep_blank_values=True); d = dict(pairs)
    if not hmac.compare_digest(pf_signature([(k, v) for k, v in pairs if k != "signature"], os.getenv("PAYFAST_PASSPHRASE", "")), d.get("signature", "")): raise PermissionError("Invalid signature")
    if d.get("merchant_id") != os.getenv("PAYFAST_MERCHANT_ID", "10000100"): raise PermissionError("Merchant mismatch")
    r = httpx.post(PF_HOST() + "/eng/query/validate", content=raw, headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=15)
    if r.text.strip() != "VALID": raise PermissionError("PayFast did not confirm this notification")
    status = {"COMPLETE": "PAID", "FAILED": "FAILED", "CANCELLED": "CANCELLED"}.get(d.get("payment_status"), "PENDING")
    return process_event(s, d.get("pf_payment_id") or d["m_payment_id"], d["m_payment_id"], status, d.get("amount_gross", "0"))
