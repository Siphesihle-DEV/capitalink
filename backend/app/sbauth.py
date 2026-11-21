"""Supabase Auth (GoTrue) adapter. Active only when SUPABASE_URL is set; otherwise the app uses local JWT auth."""
import os, time, logging, httpx, jwt
from fastapi import HTTPException

URL = lambda: os.getenv("SUPABASE_URL", "").rstrip("/")
enabled = lambda: bool(URL())
ANON = lambda: os.getenv("SUPABASE_ANON_KEY", "")
SERVICE = lambda: os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
_jwks = None; _cache = {}; log = logging.getLogger("uvicorn.error")

def _local(token: str) -> str:
    global _jwks
    secret = os.getenv("SUPABASE_JWT_SECRET")
    if secret:
        return jwt.decode(token, secret, algorithms=["HS256"], audience="authenticated")["sub"]
    _jwks = _jwks or jwt.PyJWKClient(f"{URL()}/auth/v1/.well-known/jwks.json")
    key = _jwks.get_signing_key_from_jwt(token).key
    return jwt.decode(token, key, algorithms=["ES256", "RS256"], audience="authenticated")["sub"]

def verify(token: str) -> str:
    """Returns the Supabase user id. Tries local verification (HS256 secret or JWKS); if that fails, asks Supabase itself,
    which works for any signing-key setup. Results are cached for 60s."""
    hit = _cache.get(token)
    if hit and hit[1] > time.time(): return hit[0]
    try:
        sub = _local(token)
    except Exception as e:
        log.warning("Local token check failed (%s: %s); asking Supabase /auth/v1/user", type(e).__name__, e)
        r = httpx.get(f"{URL()}/auth/v1/user", headers={"apikey": ANON(), "Authorization": f"Bearer {token}"}, timeout=10)
        if r.status_code != 200: raise ValueError(f"Supabase rejected the token ({r.status_code})")
        sub = r.json()["id"]
    if len(_cache) > 500: _cache.clear()
    _cache[token] = (sub, time.time() + 60)
    return sub

def _call(path, body, key, params=None):
    try:
        r = httpx.post(f"{URL()}/auth/v1{path}", params=params, json=body, headers={"apikey": key, **({"Authorization": f"Bearer {key}"} if key.startswith("eyJ") else {})}, timeout=20)
    except httpx.HTTPError:
        raise HTTPException(502, "Authentication service unreachable")
    data = r.json() if r.content else {}
    if r.status_code >= 400:
        raise HTTPException(400 if r.status_code < 500 else 502, data.get("msg") or data.get("error_description") or data.get("message") or "Authentication failed")
    return data

def signup(email, password, name):
    d = _call("/signup", {"email": email, "password": password, "data": {"name": name}}, ANON())
    uid = (d.get("user") or d).get("id")
    return uid, (d if d.get("access_token") else None)  # no session => email confirmation required

def login(email, password):
    d = _call("/token", {"email": email, "password": password}, ANON(), {"grant_type": "password"})
    return d["user"]["id"], d["access_token"]

def recover(email): _call("/recover", {"email": email}, ANON())

def admin_create(email, password, name):
    """Server-side creation of a pre-confirmed user (used by seed.py). Returns the user id."""
    try: return _call("/admin/users", {"email": email, "password": password, "email_confirm": True, "user_metadata": {"name": name}}, SERVICE())["id"]
    except HTTPException: return login(email, password)[0]  # already exists
