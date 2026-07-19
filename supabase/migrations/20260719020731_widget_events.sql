-- widget_events — per-request observability for the live widget-minting hot path
-- (POST /api/widget and POST /api/region). Populated by serve.py on every request,
-- read by GET /agent/perf → the ?view=perf dashboard.
--
-- Non-blocking write: serve.py fires this insert on a background thread so the
-- response returns before the log lands. Rows can be missed on process kill; that's
-- fine for perf telemetry.

create table if not exists widget_events (
  id                  bigserial primary key,
  handle              text,                      -- AGENT_HANDLE, per-user filter
  video_id            text,                      -- soft ref to videos.video_id
  t_s                 double precision,          -- position in the video
  frame_file          text,                      -- e.g. f_000120.jpg
  kind                text not null,             -- 'widget' | 'region'
  t_cache_lookup_ms   int,                       -- Supabase inference_cache lookup
  t_backend_ask_ms    int,                       -- VLM (LM Studio) call — the fat one
  t_parse_validate_ms int,                       -- extract_json + valid()
  t_total_ms          int not null,              -- end-to-end wall clock
  cache_hit           boolean not null default false,
  model               text,                      -- what LM Studio was serving
  spec_valid          boolean,                   -- did the VLM emit a manipulable widget?
  widget_kind         text,                      -- matrix_mul | attention | … | 'none' | 'answer'
  error               text,                      -- short error message if the request failed
  created_at          timestamptz not null default now()
);

create index if not exists widget_events_handle_time_idx on widget_events (handle, created_at desc);
create index if not exists widget_events_time_idx        on widget_events (created_at desc);
