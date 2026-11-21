# CapitaLink: AI-assisted SME financing (South Africa, ZAR)

Investor funds an industry pool -> SME applies -> Gemini reads the bank statements -> admin approves -> capital allocated pro-rata ->
admin confirms the EFT payout -> SME repays -> investors receive principal and interest -> events recorded on Avalanche Fuji.

## 1. Supabase (SQL editor)
1. Run `supabase/00_reset.sql` (only if you ran an older version; it deletes CapitaLink tables), then `supabase/01_schema.sql`, then `supabase/02_storage.sql` (private bucket).
2. Authentication > Providers > Email: keep "Confirm email" on. Under Users, delete any old test users from earlier versions.
3. Register your accounts in the app (investor, SME), then run `supabase/03_roles.sql` to create your administrator.
   (Or run `python seed.py` to create three starter accounts: admin@example.com, investor@example.com, sme@example.com, password `capitalink123`.)

## 2. Run
```
copy .env.example .env          (Mac/Linux: cp)   then fill in .env
cd backend && pip install -r requirements.txt && python seed.py && uvicorn app.main:app --reload
cd frontend && copy .env.example .env && npm install && npm run dev      -> http://localhost:5173
```
`GET http://localhost:8000/health` shows which services are active (db, auth, storage, payments, gemini, chain).

## 3. Demo script
1. Investor: Fund a pool -> pick Agriculture (searchable), choose an amount -> Continue to payment -> choose a bank -> Pay.
2. SME: Business profile (dropdowns and date picker) -> Documents: upload `samples/bank_statement_12_months.pdf` -> Apply -> Analyse -> confirm figures -> Submit.
3. Admin: Applications -> open -> review AI assessment, extracted monthly table, funding preview -> Approve and allocate.
4. Admin: Loans -> Confirm payout (enter the EFT reference) -> repayment schedule starts.
5. SME: Financing -> Make a repayment -> pay. Investor: Investments and Statement update. Both can print a statement (Statement tab -> Print / save as PDF).
6. Admin: Blockchain tab shows Fuji transactions (when configured).

## Payments
`PAYMENT_PROVIDER=sandbox` (default): built-in checkout page (Instant EFT / card), signed and idempotent; a small "Sandbox environment" tag shows in the sidebar.
`PAYMENT_PROVIDER=payfast`: redirects to PayFast (sandbox merchant details are public; get your own for live). PayFast must be able to reach `API_PUBLIC_URL/payments/webhook/payfast`
(deployed backend or ngrok). The notification is verified (signature, merchant, amount, PayFast server confirmation) before anything is credited. This adapter is untested against PayFast.
Binance Pay needs merchant approval and is not integrated.

## Notes
- Gemini reads the statements; averages, variation and findings are computed in code. If analysis fails, the app shows the exact reason (bad key, quota, unreadable file) and a Try again button.
- Real-money use needs legal and compliance approval (lending / pooled funds), a licensed payment provider account, and bank reconciliation of payouts.
- Contract: `cd contracts && npm install && npm test && npm run deploy:fuji` (needs a funded Fuji wallet key in .env). Untested here.
- Tests: `cd backend && pytest`.
