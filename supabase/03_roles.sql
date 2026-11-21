-- Run AFTER the person has registered in the app (or been created under Authentication > Users).
-- 1) Give an existing Supabase Auth user a CapitaLink profile (role: investor | sme | admin). Change the email, name and role.
insert into users (id, email, name, role)
select id::text, email, 'Full Name', 'admin' from auth.users where email = 'you@example.com'
on conflict (email) do update set role = excluded.role;
-- 2) Or promote someone who already registered in the app:
-- update users set role = 'admin' where email = 'you@example.com';
