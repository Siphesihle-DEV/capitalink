"""Creates three starter accounts (in Supabase Auth when configured). Run: python seed.py"""
from app.main import *
ACCOUNTS = [("admin@example.com", "Nomsa Khumalo", "admin"), ("investor@example.com", "Thandi Mokoena", "investor"), ("sme@example.com", "Sipho Dlamini", "sme")]
with SessionLocal() as s:
    for email, name, role in ACCOUNTS:
        if not s.query(User).filter(User.email == email).first():
            sid = sbauth.admin_create(email, "capitalink123", name) if sbauth.enabled() else None
            s.add(User(**({"id": sid} if sid else {}), email=email, name=name, role=role, pw="supabase-auth" if sid else hash_pw("capitalink123")))
    s.commit(); print("Accounts ready (password capitalink123):", ", ".join(e for e, _, _ in ACCOUNTS))
