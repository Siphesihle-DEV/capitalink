import { useState } from "react"; import { toneOf, label } from "./api";
export const Page = ({ title, desc, actions, children }: any) => <><div className="head"><div><h1>{title}</h1>{desc && <p>{desc}</p>}</div><div className="noprint">{actions}</div></div>{children}</>;
export const Card = ({ title, actions, children, flush }: any) => <div className="card">{title && <header><h2>{title}</h2><div>{actions}</div></header>}<div className={flush ? "" : "body"}>{children}</div></div>;
export const Stat = ({ label, value }: any) => <div className="stat"><div className="l">{label}</div><div className="v">{value}</div></div>;
export const Pill = ({ s, children }: any) => <span className={"pill " + toneOf(s)}>{children ?? label(s)}</span>;
export const Notice = ({ kind = "ok", children }: any) => children ? <div className={"notice " + kind}>{children}</div> : null;
export const Empty = ({ children }: any) => <div className="empty">{children}</div>;
export const Field = ({ label, hint, children }: any) => <label className="f"><span>{label}</span>{children}{hint && <small>{hint}</small>}</label>;
export const List = ({ items }: any) => items?.length ? <ul className="l">{items.map((x: string, i: number) => <li key={i}>{x}</li>)}</ul> : <p className="muted">None identified.</p>;
export function Combo({ value, onChange, options, placeholder = "Search…" }: any) {
  const [open, setOpen] = useState(false); const [q, setQ] = useState("");
  const list = options.filter((o: string) => o.toLowerCase().includes(q.toLowerCase()));
  return (
    <div className="combo" onBlur={(e) => { if (!e.currentTarget.contains(e.relatedTarget as Node)) setOpen(false); }}>
      <input value={open ? q : value || ""} placeholder={value || placeholder} onFocus={() => { setOpen(true); setQ(""); }} onChange={(e) => setQ(e.target.value)} />
      {open && <div className="menu">{list.length ? list.map((o: string) => <button type="button" key={o} className={o === value ? "on" : ""} onMouseDown={(e) => e.preventDefault()} onClick={() => { onChange(o); setOpen(false); }}>{o}</button>) : <div className="muted pad">No matches</div>}</div>}
    </div>
  );
}
export const Chips = ({ values, current, onPick, fmt }: any) => <div className="chips">{values.map((v: any) => <button type="button" key={v} className={"chip" + (String(current) === String(v) ? " on" : "")} onClick={() => onPick(v)}>{fmt ? fmt(v) : v}</button>)}</div>;
export const Money = ({ value, onChange, presets = [] }: any) => <><input type="number" min="0" step="100" value={value} onChange={(e) => onChange(e.target.value)} placeholder="Amount in rand" /><Chips values={presets} current={value} onPick={onChange} fmt={(v: number) => "R " + v.toLocaleString("en-ZA")} /></>;
