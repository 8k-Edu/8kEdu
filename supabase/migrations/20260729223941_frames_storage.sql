-- Keyframe pixels become durable. Until now data/<videoId>/frames/*.jpg was a purely
-- local ffmpeg artifact (gitignored), so a cache miss on any other machine was
-- unrecoverable: serve.py returned "this video's keyframes aren't on disk".
-- public.frames has existed since the initial schema and was never written to.

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('frames', 'frames', false, 4194304, array['image/jpeg'])
on conflict (id) do nothing;

-- No storage.objects policy is added on purpose. Reads go through serve.py with
-- SUPABASE_SECRET_KEY, which authenticates as service_role and bypasses RLS; the
-- browser never touches the bucket. Adding a policy here would open a path around that.

-- frames shipped with `grant all ... to anon`, so any visitor holding the publishable
-- key could enumerate and DELETE every storage_path. Same lockdown as credit_ledger.
revoke all on public.frames from anon, authenticated;
grant all on public.frames to service_role;
alter table public.frames enable row level security;

alter table widget_events add column if not exists t_frame_fetch_ms int;
alter table widget_events add column if not exists frame_source text;   -- local | remote | miss | off
