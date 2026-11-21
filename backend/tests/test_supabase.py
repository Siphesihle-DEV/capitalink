"""Supabase auth + storage paths against mocked Supabase HTTP (no network). Real-project checks are in the README."""
import os, tempfile, jwt, uuid
os.environ.setdefault("DATABASE_URL", f"sqlite:///{tempfile.mkdtemp()}/s.db")
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from app.main import app
c = TestClient(app)
SECRET = "x" * 40
def resp(code, data): m = MagicMock(); m.status_code = code; m.content = b"1"; m.json.return_value = data; m.raise_for_status = lambda: None; return m

def test_supabase_auth_and_private_storage(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co"); monkeypatch.setenv("SUPABASE_JWT_SECRET", SECRET)
    sid = str(uuid.uuid4()); tok = jwt.encode({"sub": sid, "aud": "authenticated"}, SECRET, "HS256")
    blob = {}
    def post(url, **kw):
        if url.endswith("/signup"): return resp(200, {"id": sid})                      # email confirmation required: no session
        if url.endswith("/token"): return resp(200, {"access_token": tok, "user": {"id": sid}})
        if "/storage/v1/object/" in url: blob["data"] = kw["content"]; return resp(200, {})
    with patch("app.sbauth.httpx.post", post), patch("app.storage.httpx.post", post), patch("app.storage.httpx.get", lambda *a, **k: MagicMock(content=blob["data"], raise_for_status=lambda: None)):
        r = c.post("/auth/register", json={"email": "S@t.io", "password": "password1", "name": "S", "role": "sme"}).json()
        assert "confirm your account" in r["message"].lower()
        r = c.post("/auth/login", json={"email": "s@t.io", "password": "password1"}).json()
        h = {"Authorization": "Bearer " + r["token"]}; assert r["user"]["role"] == "sme"
        assert c.post("/auth/register", json={"email": "a@t.io", "password": "password1", "name": "a", "role": "admin"}).status_code == 400  # no self-service admin
        bad = {"Authorization": "Bearer " + jwt.encode({"sub": sid, "aud": "authenticated"}, "wrong" * 10, "HS256")}
        with patch("app.sbauth.httpx.get", lambda *a, **k: resp(401, {})): assert c.get("/sme/profile", headers=bad).status_code == 401  # Supabase rejects it too
        with patch("app.sbauth.httpx.get", lambda *a, **k: resp(200, {"id": sid})): assert c.get("/sme/profile", headers=bad).status_code == 200  # secret unset/wrong but Supabase vouches for it
        c.put("/sme/profile", json={"business_name": "B", "industry": "Technology"}, headers=h)
        d = c.post("/sme/documents", data={"kind": "Bank statement"}, files={"file": ("a.pdf", b"%PDF-1", "application/pdf")}, headers=h).json()
        assert c.get(f"/documents/{d['id']}", headers=h).content == b"%PDF-1" and c.get(f"/documents/{d['id']}").status_code == 401
