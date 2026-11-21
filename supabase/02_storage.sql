-- Private bucket for uploaded business documents (the backend reads/writes it with the service key; there are no public policies).
insert into storage.buckets (id, name, public) values ('documents', 'documents', false) on conflict (id) do nothing;
