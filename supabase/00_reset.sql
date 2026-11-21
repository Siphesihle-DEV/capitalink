-- CapitaLink: RESET. Deletes every CapitaLink table and all data in them. Only run this if you want a clean start
-- (for example if you ran an earlier version of the app against this project). It does not touch Supabase Auth users.
drop table if exists audit_logs, chain_txs, webhook_events, payment_orders, distributions, repayments, instalments,
  loans, allocations, applications, documents, smes, contributions, settings, users cascade;
