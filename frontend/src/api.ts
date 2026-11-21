const BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";
export const session = {
  get: () => JSON.parse(localStorage.getItem("cl") || "null"),
  set: (v: any) => localStorage.setItem("cl", JSON.stringify(v)),
  clear: () => localStorage.removeItem("cl"),
};
export async function api(path: string, opts: { method?: string; body?: any; form?: FormData } = {}) {
  const headers: any = {}; const s = session.get();
  if (s) headers.Authorization = "Bearer " + s.token;
  if (opts.body) headers["Content-Type"] = "application/json";
  const r = await fetch(BASE + path, { method: opts.method || (opts.body || opts.form ? "POST" : "GET"), headers, body: opts.form || (opts.body ? JSON.stringify(opts.body) : undefined) });
  const data = await r.json().catch(() => null);
  if (r.status === 401 && s) { session.clear(); location.href = "/login"; }
  if (!r.ok) throw new Error(typeof data?.detail === "string" ? data.detail : "Request failed");
  return data;
}
const zar = new Intl.NumberFormat("en-ZA", { style: "currency", currency: "ZAR" });
export const money = (v: any) => zar.format(Number(v || 0));
export const fmtDate = (s: any) => (s ? new Date(s).toLocaleDateString("en-ZA", { day: "2-digit", month: "short", year: "numeric" }) : "");
export const iso = (d: Date) => d.toISOString().slice(0, 10);
export const openDoc = async (id: string) => {
  const r = await fetch(`${BASE}/documents/${id}`, { headers: { Authorization: "Bearer " + session.get().token } });
  window.open(URL.createObjectURL(await r.blob()));
};
export const toneOf = (s: string) => ({ approved: "green", paid: "green", active: "green", repaid: "green", confirmed: "green", submitted: "blue", pending_disbursement: "amber", info_requested: "amber", pending: "amber", draft: "", rejected: "red", failed: "red", cancelled: "red", "Low Risk": "green", "Moderate Risk": "amber", "High Risk": "red", "Insufficient Information": "" } as any)[s] ?? "";
export const label = (s: string) => ({ pending_disbursement: "Awaiting payout", info_requested: "Info requested" } as any)[s] || (s ? s[0].toUpperCase() + s.slice(1).replace(/_/g, " ") : "");
export const COUNTRIES = ["South Africa", "Botswana", "Namibia", "Zimbabwe", "Mozambique", "Lesotho", "Eswatini", "Zambia", "Malawi", "Kenya", "Nigeria", "Ghana", "Uganda", "Tanzania", "Rwanda", "Egypt", "Morocco", "Other"];
export const PROVINCES = ["Eastern Cape", "Free State", "Gauteng", "KwaZulu-Natal", "Limpopo", "Mpumalanga", "North West", "Northern Cape", "Western Cape"];
export const BANKS = ["FNB", "Standard Bank", "Absa", "Nedbank", "Capitec", "Discovery Bank", "TymeBank", "African Bank", "Investec"];
export function goCheckout(o: any, nav: any) {
  const c = o.checkout; if (c.type === "internal") return nav(c.url);
  const f = document.createElement("form"); f.method = "POST"; f.action = c.action;
  Object.entries(c.fields).forEach(([k, v]) => { const i = document.createElement("input"); i.type = "hidden"; i.name = k; i.value = String(v); f.appendChild(i); });
  document.body.appendChild(f); f.submit();
}
