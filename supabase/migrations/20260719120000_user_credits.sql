-- BYOK keys never touch Postgres; serve.py holds them only for its process lifetime.

alter table public.learners add column if not exists credits integer not null default 20;
revoke all on public.learners from anon, authenticated;
grant select (user_id, handle, created_at), insert (handle) on public.learners to anon, authenticated;

create table if not exists public.credit_ledger (
  id bigint generated always as identity primary key,
  user_id uuid not null references public.learners(user_id) on delete cascade,
  delta integer not null,
  reason text not null,
  model text,
  created_at timestamptz not null default now()
);
create index if not exists credit_ledger_user_idx on public.credit_ledger(user_id, created_at desc);

revoke all on public.credit_ledger from anon, authenticated;
grant all on public.credit_ledger to service_role;
grant usage, select on all sequences in schema public to service_role;
