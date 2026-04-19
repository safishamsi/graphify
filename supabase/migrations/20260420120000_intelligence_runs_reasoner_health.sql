-- depOS: surface reasoner health on intelligence_runs so the UI and ops
-- queries can distinguish a "0 findings because all looked clean" run from a
-- "0 findings because every reasoner call failed" run. Before this migration
-- both produced identical rows, which is the failure mode that caused the
-- Gemma 4 dataset run to be marked successful despite 48 silent failures.

alter table public.intelligence_runs
    add column if not exists reasoner_run_health text not null default 'ok'
        check (reasoner_run_health in ('ok', 'degraded', 'failed')),
    add column if not exists reasoner_health_reason text not null default '',
    add column if not exists reasoner_attempts integer not null default 0,
    add column if not exists reasoner_successes integer not null default 0,
    add column if not exists reasoner_failures integer not null default 0,
    add column if not exists reasoner_failure_breakdown jsonb not null default '{}'::jsonb,
    add column if not exists evidence_summary jsonb not null default '{}'::jsonb,
    add column if not exists bundles_built integer not null default 0,
    add column if not exists bundles_sent_to_reasoner integer not null default 0,
    add column if not exists bundles_skipped_low_evidence integer not null default 0,
    add column if not exists dataset_path_resolution jsonb not null default '{}'::jsonb;

-- Index that lets the operations console quickly find degraded/failed runs.
-- Partial index keeps the "ok" majority out, since they are the uninteresting
-- common case.
create index if not exists intelligence_runs_reasoner_health_idx
    on public.intelligence_runs (org_id, started_at desc)
    where reasoner_run_health <> 'ok';
