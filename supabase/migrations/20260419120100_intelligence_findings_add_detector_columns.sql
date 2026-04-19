alter table public.intelligence_findings
    alter column mode drop not null;

alter table public.intelligence_findings
    drop constraint if exists intelligence_findings_mode_check;

alter table public.intelligence_findings
    add constraint intelligence_findings_mode_check
    check (mode is null or mode in ('A', 'B', 'C'));

alter table public.intelligence_findings
    add column if not exists detector_name text not null default 'legacy',
    add column if not exists detector_version text not null default '0',
    add column if not exists pipeline_version text not null default '0',
    add column if not exists severity text not null default 'medium'
    check (severity in ('info', 'low', 'medium', 'high', 'critical'));

create index if not exists intelligence_findings_run_detector_idx
    on public.intelligence_findings (run_id, detector_name);
