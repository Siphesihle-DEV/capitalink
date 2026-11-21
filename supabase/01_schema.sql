-- CapitaLink schema. Run once in the Supabase SQL editor (after 00_reset.sql if you have an older version).
-- All money columns are numeric(18,2) in South African rand. Ids are text (uuid strings); users.id equals the Supabase Auth user id.

create table users (
  id text primary key,
  email text not null unique,
  name text,
  pw text not null default 'supabase-auth',
  role text not null check (role in ('investor','sme','admin')),
  is_demo integer default 0
);

create table contributions (
  id text primary key,
  investor_id text not null references users(id),
  industry text not null,
  amount numeric(18,2) not null check (amount > 0),
  allocated numeric(18,2) not null default 0,
  ref text,
  created timestamp not null default now(),
  check (allocated >= 0 and allocated <= amount)
);

create table smes (
  id text primary key,
  user_id text not null unique references users(id),
  business_name text, reg_number text, industry text, description text, country text, location text,
  established text, employees integer,
  monthly_revenue numeric(18,2), monthly_expenses numeric(18,2), monthly_debt numeric(18,2) default 0,
  contact text
);

create table documents (
  id text primary key,
  sme_id text not null references smes(id),
  kind text, filename text, path text, mime text
);

create table applications (
  id text primary key,
  sme_id text not null references smes(id),
  industry text,
  amount numeric(18,2) not null check (amount > 0),
  purpose text, use_of_funds text, months integer not null check (months > 0), comments text,
  status text not null default 'draft' check (status in ('draft','submitted','info_requested','approved','rejected')),
  assessment text,
  approved_amount numeric(18,2), decision_notes text, decided_by text,
  created timestamp not null default now()
);

create table allocations (
  id text primary key,
  application_id text not null references applications(id),
  contribution_id text not null references contributions(id),
  investor_id text, amount numeric(18,2) not null check (amount > 0), outstanding numeric(18,2) not null check (outstanding >= 0)
);

create table loans (
  id text primary key,
  application_id text not null unique references applications(id),
  sme_id text, principal numeric(18,2) not null check (principal > 0), rate_pct numeric(18,2), months integer,
  interest numeric(18,2), total_due numeric(18,2), principal_outstanding numeric(18,2) check (principal_outstanding >= 0),
  repaid numeric(18,2) not null default 0 check (repaid >= 0),
  status text not null default 'pending_disbursement' check (status in ('pending_disbursement','active','repaid','defaulted')),
  disbursement_ref text, disbursed_at timestamp,
  created timestamp not null default now()
);

create table instalments (
  id text primary key,
  loan_id text not null references loans(id),
  n integer, due date, amount numeric(18,2), paid numeric(18,2) default 0
);

create table repayments (
  id text primary key,
  loan_id text not null references loans(id),
  amount numeric(18,2), principal_part numeric(18,2), interest_part numeric(18,2), fee numeric(18,2),
  ref text unique, created timestamp not null default now()
);

create table distributions (
  id text primary key,
  repayment_id text not null references repayments(id),
  loan_id text, investor_id text, contribution_id text,
  principal numeric(18,2), interest numeric(18,2), fee numeric(18,2)
);

create table payment_orders (
  id text primary key,
  ref text unique, kind text check (kind in ('contribution','repayment')),
  user_id text, amount numeric(18,2), industry text, loan_id text,
  status text not null default 'pending' check (status in ('pending','paid','failed','cancelled','expired','mismatch')),
  provider text default 'sandbox', created timestamp not null default now()
);

create table webhook_events (event_id text primary key, payload text, created timestamp not null default now());

create table chain_txs (
  id text primary key,
  event text, ref text, tx_hash text, block integer,
  status text check (status in ('pending','confirmed','failed','skipped')),
  note text, created timestamp not null default now()
);

create table audit_logs (id text primary key, actor text, action text, detail text, created timestamp not null default now());

create table settings (key text primary key, value text);
insert into settings (key, value) values ('rate_pct','12'), ('platform_fee_pct','10'), ('allocation_policy','pro_rata'), ('max_months','24');

create index on contributions (investor_id); create index on contributions (industry);
create index on documents (sme_id); create index on applications (sme_id); create index on applications (status);
create index on allocations (application_id); create index on allocations (investor_id);
create index on loans (sme_id); create index on instalments (loan_id); create index on repayments (loan_id);
create index on distributions (investor_id); create index on distributions (loan_id); create index on payment_orders (user_id);

-- Security: the app reaches the database only through the backend. Lock every table against the public Data API.
alter table users enable row level security; alter table contributions enable row level security; alter table smes enable row level security;
alter table documents enable row level security; alter table applications enable row level security; alter table allocations enable row level security;
alter table loans enable row level security; alter table instalments enable row level security; alter table repayments enable row level security;
alter table distributions enable row level security; alter table payment_orders enable row level security; alter table webhook_events enable row level security;
alter table chain_txs enable row level security; alter table audit_logs enable row level security; alter table settings enable row level security;
revoke all on all tables in schema public from anon, authenticated;
alter default privileges in schema public revoke all on tables from anon, authenticated;
