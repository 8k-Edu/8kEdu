-- Per-request timings for /api/widget + /api/region, written by serve.py's telemetry
-- queue and read by GET /agent/perf. Lossy by design: events may be dropped under load
-- or on process kill, which is fine for perf telemetry.

create table if not exists widget_events (
  id                  bigserial primary key,
  handle              text,
  video_id            text,
  t_s                 double precision,
  frame_file          text,
  kind                text not null,             -- 'widget' | 'region'
  t_cache_lookup_ms   int,
  t_backend_ask_ms    int,
  t_parse_validate_ms int,
  t_total_ms          int not null,
  cache_hit           boolean not null default false,
  model               text,
  spec_valid          boolean,
  widget_kind         text,
  error               text,
  created_at          timestamptz not null default now()
);

create index if not exists widget_events_handle_time_idx on widget_events (handle, created_at desc);
create index if not exists widget_events_time_idx        on widget_events (created_at desc);
