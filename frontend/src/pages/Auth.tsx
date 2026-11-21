import { useState } from "react"; import { api, session } from "../api"; import { Field, Notice } from "../ui";
export default function Auth({ onAuth }: any) {
  const [reg, setReg] = useState(false); const [f, setF] = useState<any>({ role: "investor" }); const [err, setErr] = useState(""); const [note, setNote] = useState("");
  const set = (k: string) => (e: any) => setF({ ...f, [k]: e.target.value });
  const go = async () => { setErr(""); try { const r = await api(reg ? "/auth/register" : "/auth/login", { body: f }); if (r.message) { setNote(r.message); setReg(false); return; } session.set(r); onAuth(r.user); } catch (e: any) { setErr(e.message); } };
  return (
    <div className="auth"><div className="authbox">
      <div className="logo" style={{ justifyContent: "center", fontSize: 16 }}><i />CapitaLink</div>
      <div className="card"><h1 style={{ fontSize: 17 }}>{reg ? "Create your account" : "Sign in"}</h1><p className="muted small" style={{ margin: "4px 0 14px" }}>SME financing with AI-assisted assessment and human approval. Funding is subject to assessment, available capital and applicable regulations.</p>
        <Notice kind="err">{err}</Notice><Notice>{note}</Notice>
        <div style={{ display: "grid", gap: 12 }}>
          {reg && <><Field label="Full name"><input onChange={set("name")} /></Field>
            <Field label="I am a"><div className="seg">{[["investor", "Capital provider"], ["sme", "SME applicant"]].map(([v, l]) => <button key={v} type="button" className={f.role === v ? "on" : ""} onClick={() => setF({ ...f, role: v })}>{l}</button>)}</div></Field></>}
          <Field label="Email"><input type="email" onChange={set("email")} /></Field><Field label="Password"><input type="password" onChange={set("password")} onKeyDown={(e) => e.key === "Enter" && go()} /></Field></div>
        <div className="actions"><button className="btn" onClick={go}>{reg ? "Create account" : "Sign in"}</button>
          <button className="btn alt" onClick={() => { setReg(!reg); setErr(""); setNote(""); }}>{reg ? "I have an account" : "Create account"}</button>
          {!reg && <button className="btn alt" onClick={async () => { try { setNote((await api("/auth/reset", { body: { email: f.email } })).message); setErr(""); } catch (e: any) { setErr(e.message); } }}>Forgot password</button>}</div></div>
    </div></div>
  );
}
