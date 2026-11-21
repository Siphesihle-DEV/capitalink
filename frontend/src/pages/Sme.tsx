import { useEffect, useState } from "react"; import { useNavigate } from "react-router-dom"; import { Building2, Upload, Send, ClipboardList, Landmark, FileText } from "lucide-react";
import { api, money, fmtDate, goCheckout, COUNTRIES, PROVINCES } from "../api"; import { Shell } from "./Shell"; import Statement from "./Statement";
import { Page, Card, Stat, Pill, Notice, Empty, Field, Combo, Money, Chips, List } from "../ui";
const EMPTY = { business_name: "", reg_number: "", industry: "", description: "", country: "South Africa", location: "", established: "", employees: 1, monthly_revenue: "", monthly_expenses: "", monthly_debt: "", contact: "" };
const PURPOSES = ["Working capital", "Buy stock or inventory", "Equipment or machinery", "Vehicle", "Expand premises", "Marketing and sales", "Hire staff", "Other"];
const DOCS = ["Bank statement", "Business registration", "Proof of address", "ID of owner or director", "Other"];
const TERMS = ["3", "6", "9", "12", "18", "24"];
export default function Sme({ user, onLogout }: any) {
  const nav = useNavigate(); const [tab, setTab] = useState("Business profile"); const [p, setP] = useState<any>(EMPTY); const [inds, setInds] = useState<string[]>([]);
  const [docs, setDocs] = useState<any[]>([]); const [apps, setApps] = useState<any[]>([]); const [loans, setLoans] = useState<any[]>([]); const [kind, setKind] = useState("Bank statement");
  const [f, setF] = useState<any>({ amount: "", purpose: "", months: "12", use_of_funds: "", comments: "" }); const [draft, setDraft] = useState<any>(null); const [conf, setConf] = useState<any>({});
  const [pay, setPay] = useState<any>({}); const [msg, setMsg] = useState(""); const [err, setErr] = useState(""); const [busy, setBusy] = useState(false);
  const load = () => { api("/sme/profile").then((r) => r && setP({ ...EMPTY, ...r })); api("/sme/documents").then(setDocs); api("/sme/applications").then(setApps); api("/sme/loans").then(setLoans); };
  useEffect(() => { load(); api("/industries").then(setInds); }, []);
  const run = async (fn: any, ok = "") => { setErr(""); setMsg(""); setBusy(true); try { await fn(); setMsg(ok); } catch (e: any) { setErr(e.message); } setBusy(false); };
  const set = (k: string) => (v: any) => setP({ ...p, [k]: v }); const inp = (k: string) => (e: any) => set(k)(e.target.value);
  const Msg = () => <><Notice kind="err">{err}</Notice><Notice>{msg}</Notice></>;
  const show = (d: any) => { setDraft(d); setConf(d.assessment.extracted); };
  const ai = draft?.assessment?.ai;
  return (
    <Shell nav={[["Business profile", Building2], ["Documents", Upload], ["Apply", Send], ["Applications", ClipboardList], ["Financing", Landmark], ["Statement", FileText]]} {...{ tab, setTab, user, onLogout }}>
      {tab === "Business profile" && <Page title="Business profile" desc="Used for every application. Formal registration is optional: informal businesses can apply."><Card>
        <div className="two"><Field label="Business name"><input value={p.business_name} onChange={inp("business_name")} /></Field><Field label="Registration number" hint="Leave blank if not registered"><input value={p.reg_number || ""} onChange={inp("reg_number")} /></Field>
          <Field label="Industry"><Combo value={p.industry} onChange={set("industry")} options={inds} placeholder="Search industries" /></Field>
          <Field label="Date established"><input type="date" max={new Date().toISOString().slice(0, 10)} value={p.established || ""} onChange={inp("established")} /></Field>
          <Field label="Country"><Combo value={p.country} onChange={set("country")} options={COUNTRIES} /></Field>
          <Field label="Province / region">{p.country === "South Africa" ? <Combo value={p.location} onChange={set("location")} options={PROVINCES} /> : <input value={p.location} onChange={inp("location")} />}</Field>
          <Field label="Employees"><input type="number" min="0" value={p.employees} onChange={inp("employees")} /></Field><Field label="Contact number"><input type="tel" value={p.contact || ""} onChange={inp("contact")} /></Field>
          <Field label="Monthly revenue (R)"><input type="number" min="0" step="500" value={p.monthly_revenue} onChange={inp("monthly_revenue")} /></Field><Field label="Monthly expenses (R)"><input type="number" min="0" step="500" value={p.monthly_expenses} onChange={inp("monthly_expenses")} /></Field>
          <Field label="Existing monthly debt payments (R)"><input type="number" min="0" step="100" value={p.monthly_debt} onChange={inp("monthly_debt")} /></Field></div>
        <div style={{ marginTop: 14 }}><Field label="What does the business do?"><textarea rows={3} value={p.description || ""} onChange={inp("description")} /></Field></div>
        <Msg /><div className="actions"><button className="btn" disabled={busy || !p.business_name || !p.industry} onClick={() => run(async () => { await api("/sme/profile", { method: "PUT", body: { ...p, employees: Number(p.employees) || 0, monthly_revenue: p.monthly_revenue || 0, monthly_expenses: p.monthly_expenses || 0, monthly_debt: p.monthly_debt || 0 } }); load(); }, "Profile saved.")}>Save profile</button></div></Card></Page>}
      {tab === "Documents" && <Page title="Documents" desc="Upload your last 12 months of bank statements. Files are stored privately and only you and the review team can open them."><Card>
        <div className="two"><Field label="Document type"><Combo value={kind} onChange={setKind} options={DOCS} /></Field><Field label="File" hint="PDF, PNG, JPEG or CSV, up to 10 MB"><input type="file" accept=".pdf,.png,.jpg,.jpeg,.csv" onChange={(e) => { const file = e.target.files?.[0]; if (file) run(async () => { const fd = new FormData(); fd.append("kind", kind); fd.append("file", file); await api("/sme/documents", { form: fd }); load(); }, "Uploaded."); e.target.value = ""; }} /></Field></div><Msg /></Card>
        <Card title="Uploaded" flush>{docs.length === 0 ? <Empty>No documents yet.</Empty> : <table><tbody>{docs.map((d) => <tr key={d.id}><td>{d.kind}</td><td>{d.filename}</td></tr>)}</tbody></table>}</Card></Page>}
      {tab === "Apply" && <Page title="Apply for financing" desc="We read your bank statements and show you what we found before you submit.">
        {!draft ? <Card><div className="two"><Field label="Amount needed (ZAR)"><Money value={f.amount} onChange={(v: any) => setF({ ...f, amount: v })} presets={[10000, 25000, 50000, 100000, 250000]} /></Field>
          <div><Field label="Repayment period"><Combo value={f.months + " months"} onChange={(v: string) => setF({ ...f, months: v.split(" ")[0] })} options={TERMS.map((t) => t + " months")} /></Field>
            <div style={{ marginTop: 14 }}><Field label="Purpose"><Combo value={f.purpose} onChange={(v: string) => setF({ ...f, purpose: v })} options={PURPOSES} placeholder="Search purposes" /></Field></div></div></div>
          <div style={{ marginTop: 14 }}><Field label="How will the money be used? (optional)"><textarea rows={2} value={f.use_of_funds} onChange={(e) => setF({ ...f, use_of_funds: e.target.value })} /></Field></div>
          <Msg />{docs.length === 0 && <Notice kind="warn">Upload a bank statement under Documents first.</Notice>}
          <div className="actions"><button className="btn" disabled={busy || !(Number(f.amount) > 0) || !f.purpose || docs.length === 0} onClick={() => run(async () => show(await api("/sme/applications", { body: { ...f, months: Number(f.months) } })))}>{busy ? "Reading your documents…" : "Analyse my documents"}</button></div></Card> : <>
          {draft.assessment.error && <Notice kind="err"><b>We could not read your documents.</b> {draft.assessment.error}<div className="actions"><button className="btn sm" disabled={busy} onClick={() => run(async () => show(await api(`/sme/applications/${draft.id}/reanalyze`, { method: "POST" })))}>Try again</button></div></Notice>}
          {!draft.assessment.error && ai.monthly.length > 0 && <Card title={`What we found in your statements (${ai.months_covered} months)`} flush><div className="tablewrap"><table><thead><tr><th>Month</th><th className="r">Money in</th><th className="r">Money out</th></tr></thead>
            <tbody>{ai.monthly.map((m: any) => <tr key={m.month}><td>{m.month}</td><td className="r">{money(m.deposits)}</td><td className="r">{money(m.withdrawals)}</td></tr>)}</tbody></table></div></Card>}
          <Card title="Confirm these monthly figures"><p className="muted">Please correct anything that looks wrong. These are the figures we use to assess affordability.</p>
            <div className="three">{[["monthly_revenue", "Monthly revenue (R)"], ["monthly_expenses", "Monthly expenses (R)"], ["monthly_debt", "Existing monthly debt payments (R)"]].map(([k, l]) => <Field key={k} label={l}><input type="number" min="0" step="100" value={conf[k]} onChange={(e) => setConf({ ...conf, [k]: e.target.value })} /></Field>)}</div></Card>
          <Card title="Preliminary feedback"><p>{ai.summary}</p><div className="two"><div><b>Positive indicators</b><List items={ai.positives} /><b>Suggestions</b><List items={ai.suggestions} /></div><div><b>Areas to improve</b><List items={ai.risks} /><b>Missing information</b><List items={ai.missing_information} /></div></div>
            <p className="muted small">{draft.assessment.disclaimer}</p></Card>
          <Msg /><div className="actions" style={{ marginTop: 0 }}><button className="btn" disabled={busy} onClick={() => run(async () => { await api(`/sme/applications/${draft.id}/submit`, { body: conf }); setDraft(null); setF({ amount: "", purpose: "", months: "12", use_of_funds: "", comments: "" }); load(); setTab("Applications"); })}>Confirm and submit application</button><button className="btn alt" onClick={() => setDraft(null)}>Start over</button></div></>}
      </Page>}
      {tab === "Applications" && <Page title="Applications" desc="Track every application from submission to decision."><Card flush>{apps.length === 0 ? <Empty>No applications yet.</Empty> :
        <div className="tablewrap"><table><thead><tr><th>Submitted</th><th>Purpose</th><th className="r">Requested</th><th>Status</th><th className="r">Approved</th><th>Reviewer notes</th></tr></thead>
          <tbody>{apps.map((a) => <tr key={a.id}><td>{fmtDate(a.created)}</td><td>{a.purpose}</td><td className="r">{money(a.amount)}</td><td><Pill s={a.status} /></td><td className="r">{a.approved_amount ? money(a.approved_amount) : ""}</td><td className="muted">{a.decision_notes}</td></tr>)}</tbody></table></div>}</Card></Page>}
      {tab === "Financing" && <Page title="Financing & repayments">{loans.length === 0 ? <Card><Empty>No approved financing yet.</Empty></Card> : loans.map((l) => <div key={l.id}>
        <div className="grid"><Stat label="Approved amount" value={money(l.principal)} /><Stat label="Interest rate" value={Number(l.rate_pct) + "% p.a."} /><Stat label="Total to repay" value={money(l.total_due)} /><Stat label="Repaid so far" value={money(l.repaid)} /><Stat label="Principal outstanding" value={money(l.principal_outstanding)} /></div>
        {l.status === "pending_disbursement" ? <Notice kind="warn">Your financing is approved. We will pay it out to your bank account and confirm here. Repayments open once it has been paid out.</Notice> :
          <Notice>Paid out on {fmtDate(l.disbursed_at)} · bank reference <span className="mono">{l.disbursement_ref}</span> · <Pill s={l.status} /></Notice>}
        {l.schedule.length > 0 && <Card title="Repayment schedule" flush><table><thead><tr><th>#</th><th>Due</th><th className="r">Amount</th><th className="r">Paid</th></tr></thead><tbody>{l.schedule.map((i: any) => <tr key={i.id}><td>{i.n}</td><td>{fmtDate(i.due)}</td><td className="r">{money(i.amount)}</td><td className="r">{money(i.paid)}</td></tr>)}</tbody></table></Card>}
        {l.status === "active" && <Card title="Make a repayment"><Msg /><Field label="Amount (ZAR)"><Money value={pay[l.id] ?? ""} onChange={(v: any) => setPay({ ...pay, [l.id]: v })} presets={[Number(l.schedule.find((i: any) => Number(i.paid) < Number(i.amount))?.amount || 0), Number(l.total_due) - Number(l.repaid)].filter((x, i, a) => x > 0 && a.indexOf(x) === i)} /></Field>
          <div className="actions"><button className="btn" disabled={busy || !(Number(pay[l.id]) > 0)} onClick={() => run(async () => goCheckout(await api("/sme/repay", { body: { loan_id: l.id, amount: pay[l.id] } }), nav))}>Continue to payment</button></div></Card>}
        {l.repayments.length > 0 && <Card title="Repayment history" flush><table><thead><tr><th>Date</th><th className="r">Amount</th><th className="r">Principal</th><th className="r">Interest</th><th>Reference</th></tr></thead><tbody>{l.repayments.map((r: any) => <tr key={r.id}><td>{fmtDate(r.created)}</td><td className="r">{money(r.amount)}</td><td className="r">{money(r.principal_part)}</td><td className="r">{money(r.interest_part)}</td><td className="mono">{r.ref}</td></tr>)}</tbody></table></Card>}
      </div>)}</Page>}
      {tab === "Statement" && <Statement endpoint="/sme/statement" user={user} />}
    </Shell>
  );
}
