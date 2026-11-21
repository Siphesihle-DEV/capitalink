import os, uuid, datetime as dt
from pathlib import Path
from dotenv import load_dotenv
for _p in (Path(__file__).resolve().parents[2] / '.env', Path(__file__).resolve().parents[1] / '.env'): load_dotenv(_p)  # repo-root or backend/.env; real env vars win
from decimal import Decimal
from sqlalchemy import create_engine, Column, String, Numeric, Integer, DateTime, ForeignKey, Text, Date
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./capitalink.db")  # Supabase: use the Postgres connection string
if DATABASE_URL.startswith("postgres://"): DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
IS_PG = DATABASE_URL.startswith("postgresql")
engine = create_engine(DATABASE_URL, pool_pre_ping=True, **({} if IS_PG else {"connect_args": {"check_same_thread": False}}))
SessionLocal = sessionmaker(bind=engine, autoflush=False)
Base = declarative_base()
M = lambda: Numeric(18, 2)
uid = lambda: str(uuid.uuid4())
now = lambda: dt.datetime.utcnow()

class User(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True, default=uid)
    email = Column(String, unique=True, nullable=False)
    name = Column(String); pw = Column(String); role = Column(String)  # investor | sme | admin
    is_demo = Column(Integer, default=0)

class Contribution(Base):
    __tablename__ = "contributions"
    id = Column(String, primary_key=True, default=uid)
    investor_id = Column(String, ForeignKey("users.id")); industry = Column(String)
    amount = Column(M()); allocated = Column(M(), default=Decimal("0"))  # allocated = currently committed principal
    ref = Column(String)  # payment reference
    created = Column(DateTime, default=now)

class Sme(Base):
    __tablename__ = "smes"
    id = Column(String, primary_key=True, default=uid)
    user_id = Column(String, ForeignKey("users.id"), unique=True)
    business_name = Column(String); reg_number = Column(String); industry = Column(String)
    description = Column(Text); country = Column(String); location = Column(String)
    established = Column(String); employees = Column(Integer)
    monthly_revenue = Column(M()); monthly_expenses = Column(M()); monthly_debt = Column(M(), default=Decimal("0"))
    contact = Column(String)

class Document(Base):
    __tablename__ = "documents"
    id = Column(String, primary_key=True, default=uid)
    sme_id = Column(String, ForeignKey("smes.id")); kind = Column(String)
    filename = Column(String); path = Column(String); mime = Column(String)

class Application(Base):
    __tablename__ = "applications"
    id = Column(String, primary_key=True, default=uid)
    sme_id = Column(String, ForeignKey("smes.id")); industry = Column(String)
    amount = Column(M()); purpose = Column(Text); use_of_funds = Column(Text)
    months = Column(Integer); comments = Column(Text)
    status = Column(String, default="draft")  # submitted | approved | rejected | info_requested
    assessment = Column(Text)  # JSON
    approved_amount = Column(M()); decision_notes = Column(Text); decided_by = Column(String)
    created = Column(DateTime, default=now)

class Allocation(Base):
    __tablename__ = "allocations"
    id = Column(String, primary_key=True, default=uid)
    application_id = Column(String, ForeignKey("applications.id"))
    contribution_id = Column(String, ForeignKey("contributions.id"))
    investor_id = Column(String); amount = Column(M()); outstanding = Column(M())

class Loan(Base):
    __tablename__ = "loans"
    id = Column(String, primary_key=True, default=uid)
    application_id = Column(String, ForeignKey("applications.id"), unique=True)
    sme_id = Column(String); principal = Column(M()); rate_pct = Column(M()); months = Column(Integer)
    interest = Column(M()); total_due = Column(M()); principal_outstanding = Column(M())
    repaid = Column(M(), default=Decimal("0")); status = Column(String, default="pending_disbursement")  # -> active -> repaid
    disbursement_ref = Column(String); disbursed_at = Column(DateTime)
    created = Column(DateTime, default=now)

class Instalment(Base):
    __tablename__ = "instalments"
    id = Column(String, primary_key=True, default=uid)
    loan_id = Column(String, ForeignKey("loans.id")); n = Column(Integer)
    due = Column(Date); amount = Column(M()); paid = Column(M(), default=Decimal("0"))

class Repayment(Base):
    __tablename__ = "repayments"
    id = Column(String, primary_key=True, default=uid)
    loan_id = Column(String, ForeignKey("loans.id")); amount = Column(M())
    principal_part = Column(M()); interest_part = Column(M()); fee = Column(M())
    ref = Column(String, unique=True); created = Column(DateTime, default=now)

class Distribution(Base):
    __tablename__ = "distributions"
    id = Column(String, primary_key=True, default=uid)
    repayment_id = Column(String, ForeignKey("repayments.id")); loan_id = Column(String)
    investor_id = Column(String); contribution_id = Column(String)
    principal = Column(M()); interest = Column(M()); fee = Column(M())

class PaymentOrder(Base):
    __tablename__ = "payment_orders"
    id = Column(String, primary_key=True, default=uid)
    ref = Column(String, unique=True); kind = Column(String)  # contribution | repayment
    user_id = Column(String); amount = Column(M()); industry = Column(String); loan_id = Column(String)
    status = Column(String, default="pending"); provider = Column(String, default="demo")
    created = Column(DateTime, default=now)

class WebhookEvent(Base):
    __tablename__ = "webhook_events"
    event_id = Column(String, primary_key=True); payload = Column(Text); created = Column(DateTime, default=now)

class ChainTx(Base):
    __tablename__ = "chain_txs"
    id = Column(String, primary_key=True, default=uid)
    event = Column(String); ref = Column(String); tx_hash = Column(String); block = Column(Integer)
    status = Column(String)  # confirmed | failed | skipped
    note = Column(Text); created = Column(DateTime, default=now)

class Audit(Base):
    __tablename__ = "audit_logs"
    id = Column(String, primary_key=True, default=uid)
    actor = Column(String); action = Column(String); detail = Column(Text); created = Column(DateTime, default=now)

class Setting(Base):
    __tablename__ = "settings"
    key = Column(String, primary_key=True); value = Column(String)

DEFAULT_SETTINGS = {"rate_pct": "12", "platform_fee_pct": "10", "allocation_policy": "pro_rata", "max_months": "24"}
INDUSTRIES = ["Agriculture", "Technology", "Retail and Wholesale", "Manufacturing", "Healthcare",
              "Education", "Transportation and Logistics", "Other Services"]

def init_db():
    if not IS_PG: Base.metadata.create_all(engine)  # on Supabase, tables come from supabase/01_schema.sql
    elif os.getenv("AUTO_CREATE_TABLES") == "1": Base.metadata.create_all(engine)
    else:
        from sqlalchemy import inspect
        if "loans" not in inspect(engine).get_table_names(): raise RuntimeError("Database tables not found. Run supabase/00_reset.sql then 01_schema.sql in the Supabase SQL editor.")
    with SessionLocal() as s:
        for k, v in DEFAULT_SETTINGS.items():
            if not s.get(Setting, k): s.add(Setting(key=k, value=v))
        s.commit()
