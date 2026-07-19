create table if not exists kg_concept (
  id bigserial primary key,
  topic text not null,
  name text not null,
  label text not null,
  exemplar_count integer not null default 0,
  best_link_id bigint,
  first_run integer not null,
  created_at timestamptz not null default now(),
  unique (topic, name)
);

create table if not exists kg_frame_link (
  id bigserial primary key,
  kg_concept_id bigint not null references kg_concept(id) on delete cascade,
  concept_id bigint references concepts(id) on delete set null,
  topic text not null,
  video_id text not null,
  video_title text,
  t_s double precision not null,
  channel text,
  widget text,
  quality real not null default 0,
  spec jsonb not null,
  created_at timestamptz not null default now(),
  unique (kg_concept_id, video_id, t_s)
);

create index if not exists kg_frame_link_topic_idx on kg_frame_link (topic);
create index if not exists kg_frame_link_video_idx on kg_frame_link (video_id);

create table if not exists kg_edge (
  topic text not null,
  src_id bigint not null references kg_concept(id) on delete cascade,
  dst_id bigint not null references kg_concept(id) on delete cascade,
  kind text not null check (kind in ('prereq', 'related')),
  weight integer not null default 1,
  primary key (topic, src_id, dst_id, kind),
  check (src_id <> dst_id)
);

create table if not exists kg_widget_prior (
  topic text not null,
  concept_name text not null,
  widget text not null,
  tried integer not null default 0,
  valid integer not null default 0,
  primary key (topic, concept_name, widget)
);

create table if not exists topic_runs (
  id bigserial primary key,
  experiment_id text,
  topic text not null,
  run_seq integer not null,
  mode text not null,
  video_id text,
  source_videos text[] not null default '{}',
  frames_total integer not null default 0,
  frames_analyzed integer not null default 0,
  vlm_calls integer not null default 0,
  widgets_new integer not null default 0,
  widgets_reused integer not null default 0,
  novel_concepts integer not null default 0,
  known_concepts integer not null default 0,
  build_ms integer not null default 0,
  yield real not null default 0,
  concept_recall real,
  retrieval_precision real,
  model text,
  prompt_version text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists topic_runs_topic_time_idx on topic_runs (topic, created_at desc);
create index if not exists topic_runs_experiment_idx on topic_runs (experiment_id, mode);

grant all on kg_concept, kg_frame_link, kg_edge, kg_widget_prior, topic_runs to anon, authenticated, service_role;
grant usage, select on all sequences in schema public to anon, authenticated, service_role;
