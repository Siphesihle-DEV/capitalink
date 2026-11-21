import { useState } from "react"; import { Routes, Route, Navigate } from "react-router-dom";
import { session } from "./api"; import Auth from "./pages/Auth"; import Investor from "./pages/Investor"; import Sme from "./pages/Sme"; import Admin from "./pages/Admin"; import Checkout from "./pages/Checkout";
export default function App() {
  const [user, setUser] = useState<any>(session.get()?.user);
  const out = () => { session.clear(); setUser(null); };
  const home = user ? "/" + user.role : "/login";
  return (
    <Routes>
      <Route path="/login" element={user ? <Navigate to={home} /> : <Auth onAuth={setUser} />} />
      <Route path="/pay/:ref" element={user ? <Checkout /> : <Navigate to="/login" />} />
      <Route path="/pay/:ref/return" element={user ? <Checkout /> : <Navigate to="/login" />} />
      <Route path="/investor" element={user?.role === "investor" ? <Investor user={user} onLogout={out} /> : <Navigate to={home} />} />
      <Route path="/sme" element={user?.role === "sme" ? <Sme user={user} onLogout={out} /> : <Navigate to={home} />} />
      <Route path="/admin" element={user?.role === "admin" ? <Admin user={user} onLogout={out} /> : <Navigate to={home} />} />
      <Route path="*" element={<Navigate to={home} />} />
    </Routes>
  );
}
