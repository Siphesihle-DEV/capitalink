import { useEffect, useState } from "react"; import { Sun, Moon, LogOut, FlaskConical } from "lucide-react"; import { api } from "../api";
export function Shell({ nav, tab, setTab, user, onLogout, children }: any) {
  const [theme, setTheme] = useState(localStorage.getItem("theme") || "dark"); const [env, setEnv] = useState("");
  useEffect(() => { document.documentElement.dataset.theme = theme; localStorage.setItem("theme", theme); }, [theme]);
  useEffect(() => { api("/health").then((h) => setEnv(h.environment)).catch(() => {}); }, []);
  const role = { investor: "Capital provider", sme: "SME", admin: "Administrator" }[user.role as string];
  return (
    <div className="app">
      <nav className="side"><div className="logo"><i />CapitaLink</div>
        {nav.map(([key, Icon]: any) => <button key={key} className={"nav" + (key === tab ? " on" : "")} onClick={() => setTab(key)}><Icon size={16} />{key}</button>)}
        <div className="sp" />
        <div className="foot">{env === "sandbox" && <div className="env"><FlaskConical size={12} />Sandbox environment</div>}<button className="nav" onClick={onLogout}><LogOut size={16} />Sign out</button></div>
      </nav>
      <div className="col">
        <header className="top"><div className="crumbs">CapitaLink / {role} / <b>{tab}</b></div><div className="sp" />
          <button className="iconbtn" title="Switch theme" onClick={() => setTheme(theme === "dark" ? "light" : "dark")}>{theme === "dark" ? <Sun size={15} /> : <Moon size={15} />}</button>
          <div className="user"><div className="avatar">{user.name?.[0]?.toUpperCase()}</div><span>{user.name}</span></div></header>
        <div className="scroll"><main className="content">{children}</main></div>
      </div>
    </div>
  );
}
