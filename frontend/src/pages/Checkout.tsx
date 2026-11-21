import { useEffect, useState } from "react"; import { useNavigate, useParams } from "react-router-dom"; import { Lock, CheckCircle2 } from "lucide-react";
import { api, money, session, BANKS } from "../api"; import { Card, Combo, Field, Notice } from "../ui";
export default function Checkout() {
  const { ref } = useParams(); const nav = useNavigate(); const role = session.get()?.user?.role;
  const [o, setO] = useState<any>(null); const [method, setMethod] = useState("eft"); const [bank, setBank] = useState(""); const [err, setErr] = useState(""); const [busy, setBusy] = useState(false);
  useEffect(() => { api(`/payments/${ref}`).then(setO).catch((e) => setErr(e.message)); }, [ref]);
  const done = () => nav("/" + role);
  const pay = async (outcome = "PAID") => { setErr(""); setBusy(true); try { setO((await api(`/payments/${ref}/pay`, { body: { method, bank, outcome } })).order); } catch (e: any) { setErr(e.message); } setBusy(false); };
  if (!o) return <div className="checkout"><Notice kind="err">{err || "Loading…"}</Notice></div>;
  const header = <><div className="muted">{o.description}</div><div className="big">{money(o.amount)}</div></>;
  let body;
  if (o.status === "paid") body = <div style={{ textAlign: "center", padding: "12px 0" }}><CheckCircle2 size={40} color="var(--brand)" /><h1 style={{ margin: "10px 0 4px" }}>Payment successful</h1><p className="muted">{money(o.amount)} · reference <span className="mono">{o.ref}</span></p><div className="actions" style={{ justifyContent: "center" }}><button className="btn" onClick={done}>Back to dashboard</button></div></div>;
  else if (o.status !== "pending") body = <><h1>Payment {o.status}</h1><p className="muted">No money was taken. Reference <span className="mono">{o.ref}</span></p><div className="actions"><button className="btn" onClick={done}>Back to dashboard</button></div></>;
  else if (o.provider === "payfast") body = <>{header}<Notice kind="warn">Waiting for the payment provider to confirm. This usually takes a few seconds.</Notice><div className="actions"><button className="btn" onClick={() => api(`/payments/${ref}`).then(setO)}>Check again</button><button className="btn alt" onClick={done}>Back to dashboard</button></div></>;
  else body = <>{header}<Notice kind="err">{err}</Notice>
    <Field label="Payment method"><div className="seg">{[["eft", "Instant EFT"], ["card", "Card"]].map(([v, l]) => <button key={v} type="button" className={method === v ? "on" : ""} onClick={() => setMethod(v)}>{l}</button>)}</div></Field>
    {method === "eft" ? <div style={{ marginTop: 14 }}><Field label="Your bank" hint="You will approve the payment with your bank."><Combo value={bank} onChange={setBank} options={BANKS} placeholder="Search for your bank" /></Field></div> : <p className="muted small" style={{ marginTop: 14 }}>Card details are entered securely with the payment provider.</p>}
    <div className="actions"><button className="btn" disabled={busy} onClick={() => pay()}><Lock size={14} />Pay {money(o.amount)}</button><button className="btn alt" disabled={busy} onClick={() => pay("CANCELLED")}>Cancel</button></div>
    <p className="muted small" style={{ marginTop: 14 }}>Reference <span className="mono">{o.ref}</span></p></>;
  return <div className="checkout"><div className="logo"><i />CapitaLink checkout</div><Card>{body}</Card></div>;
}
