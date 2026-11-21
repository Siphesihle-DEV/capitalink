import { useEffect, useState } from "react"; import { useNavigate } from "react-router-dom"; import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from "recharts";
import { LayoutDashboard, Wallet, Briefcase, FileText } from "lucide-react";
import { api, money, goCheckout } from "../api"; import { Shell } from "./Shell"; import Statement from "./Statement"; import { Page, Card, Stat, Pill, Notice, Empty, Field, Combo, Money } from "../ui";
const COLORS = ["#3ecf8e", "#1f9d68", "#6cb4ff", "#e5a93a", "#b48ead", "#8f8f8f", "#f0625a", "#5b8c7a"];
export default function Investor({ user, onLogout }: any) {
  const nav = useNavigate(); const [tab, setTab] = useState("Overview"); const [sum, setSum] = useState<any>(null); const [inv, setInv] = useState<any[]>([]); const [inds, setInds] = useState<string[]>([]);
  const [industry, setIndustry] = useState(""); const [amount, setAmount] = useState(""); const [err, setErr] = useState("");
  useEffect(() => { api("/investor/summary").then(setSum); api("/investor/investments").then(setInv); api("/industries").then(setInds); }, []);
  const go = async () => { setErr(""); try { goCheckout(await api("/investor/contribute", { body: { industry, amount } }), nav); } catch (e: any) { setErr(e.message); } };
  return (
    <Shell nav={[["Overview", LayoutDashboard], ["Fund a pool", Wallet], ["Investments", Briefcase], ["Statement", FileText]]} {...{ tab, setTab, user, onLogout }}>
      {tab === "Overview" && sum && <Page title={`Welcome, ${user.name.split(" ")[0]}`} desc="Your capital, where it is deployed, and what it has returned.">
        <div className="grid"><Stat label="Total contributed" value={money(sum.total_contributed)} /><Stat label="Available capital" value={money(sum.available)} /><Stat label="Lent out (outstanding)" value={money(sum.allocated)} />
          <Stat label="Principal returned" value={money(sum.principal_returned)} /><Stat label="Interest earned (net of fees)" value={money(sum.interest_earned)} /></div>
        <Card title="Contributions by industry">{sum.by_industry.length === 0 ? <Empty>No contributions yet. Fund an industry pool to get started.</Empty> :
          <div style={{ height: 250 }}><ResponsiveContainer><PieChart><Pie data={sum.by_industry.map((x: any) => ({ name: x.industry, value: Number(x.amount) }))} dataKey="value" nameKey="name" outerRadius={95} innerRadius={55} stroke="none">
            {sum.by_industry.map((_: any, i: number) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}</Pie><Tooltip formatter={(v: any) => money(v)} contentStyle={{ background: "var(--panel)", border: "1px solid var(--line2)", borderRadius: 6 }} /></PieChart></ResponsiveContainer></div>}</Card>
        <p className="muted small">Returns are not guaranteed. Capital is only lent within the industry you choose.</p></Page>}
      {tab === "Fund a pool" && <Page title="Fund an industry pool" desc="Your money is lent only to approved SMEs in the industry you choose."><Card>
        <Notice kind="err">{err}</Notice>
        <div className="two"><Field label="Industry"><Combo value={industry} onChange={setIndustry} options={inds} placeholder="Search industries" /></Field>
          <Field label="Amount (ZAR)"><Money value={amount} onChange={setAmount} presets={[5000, 10000, 25000, 50000, 100000]} /></Field></div>
        <div className="actions"><button className="btn" disabled={!industry || !(Number(amount) > 0)} onClick={go}>Continue to payment</button></div></Card></Page>}
      {tab === "Investments" && <Page title="Investments" desc="SMEs funded from your capital. Private business documents are never shown to investors."><Card flush>
        {inv.length === 0 ? <Empty>None of your capital has been lent out yet. It appears here when an application in your industry is approved.</Empty> :
          <div className="tablewrap"><table><thead><tr><th>Business</th><th>Industry</th><th>Purpose</th><th className="r">Allocated</th><th className="r">Outstanding</th><th className="r">Principal back</th><th className="r">Interest</th><th>Status</th></tr></thead>
            <tbody>{inv.map((i, k) => <tr key={k}><td>{i.business}</td><td>{i.industry}</td><td>{i.purpose}</td><td className="r">{money(i.allocated)}</td><td className="r">{money(i.outstanding)}</td><td className="r">{money(i.principal_returned)}</td><td className="r">{money(i.interest_earned)}</td><td><Pill s={i.loan_status} /></td></tr>)}</tbody></table></div>}</Card></Page>}
      {tab === "Statement" && <Statement endpoint="/investor/statement" user={user} />}
    </Shell>
  );
}
