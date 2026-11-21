"""Document storage: private Supabase Storage bucket when configured, local disk otherwise. Files are only served through authorised API routes."""
import os, uuid, httpx
BUCKET = lambda: os.getenv("SUPABASE_BUCKET", "documents")
SB = lambda: os.getenv("SUPABASE_URL", "").rstrip("/")
KEY = lambda: os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
HDR = lambda: {"apikey": KEY(), **({"Authorization": f"Bearer {KEY()}"} if KEY().startswith("eyJ") else {})}  # new sb_ keys are not JWTs
LOCAL = lambda: os.getenv("UPLOAD_DIR", "./uploads")

def save(data: bytes, mime: str) -> str:
    name = uuid.uuid4().hex
    if SB():
        r = httpx.post(f"{SB()}/storage/v1/object/{BUCKET()}/{name}", headers={**HDR(), "Content-Type": mime}, content=data, timeout=60)
        r.raise_for_status(); return "sb:" + name
    os.makedirs(LOCAL(), exist_ok=True); p = os.path.join(LOCAL(), name); open(p, "wb").write(data); return p

def read(path: str) -> bytes:
    if path.startswith("sb:"):
        r = httpx.get(f"{SB()}/storage/v1/object/{BUCKET()}/{path[3:]}", headers=HDR(), timeout=60); r.raise_for_status(); return r.content
    return open(path, "rb").read()
