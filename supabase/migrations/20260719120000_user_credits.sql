-- User credit system for cloud (OpenRouter) inference.
-- Local models (vLLM/Nemotron) stay free; cloud widget generation spends credits,
-- unless the learner brought their own OpenRouter key (then it's unmetered).

alter table public.learners add column if not exists credits integer not null default 20;
alter table public.learners add column if not exists openrouter_key text;

-- Ledger of credit movements (grants + cloud spends) for the dashboard / audit.
create table if not exists public.credit_ledger (
  id bigint generated always as identity primary key,
  user_id uuid not null references public.learners(user_id) on delete cascade,
  delta integer not null,
  reason text not null,
  model text,
  created_at timestamptz not null default now()
);
create index if not exists credit_ledger_user_idx on public.credit_ledger(user_id, created_at desc);

grant all on public.credit_ledger to anon, authenticated, service_role;
grant usage, select on all sequences in schema public to anon, authenticated, service_role;
