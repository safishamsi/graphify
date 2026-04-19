alter table public.intelligence_runs
    add column if not exists pipeline_version text not null default '0',
    add column if not exists ingest_errors jsonb not null default '[]'::jsonb,
    add column if not exists universes_present jsonb not null default '[]'::jsonb,
    add column if not exists enabled_detectors jsonb not null default '[]'::jsonb;
