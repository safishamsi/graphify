create table if not exists public.intelligence_detector_stats (
    run_id uuid not null references public.intelligence_runs (id) on delete cascade,
    detector_name text not null,
    detector_version text not null,
    candidates_emitted integer not null default 0,
    verified_confirmed integer not null default 0,
    verified_invalid integer not null default 0,
    mean_latency_ms numeric not null default 0,
    errors jsonb not null default '[]'::jsonb,
    primary key (run_id, detector_name)
);

alter table public.intelligence_detector_stats enable row level security;

drop policy if exists intelligence_detector_stats_member_select on public.intelligence_detector_stats;
create policy intelligence_detector_stats_member_select
    on public.intelligence_detector_stats
    for select
    to authenticated
    using (
        exists (
            select 1
            from public.intelligence_runs r
            where r.id = intelligence_detector_stats.run_id
              and public.is_org_member(r.org_id)
        )
    );

drop policy if exists intelligence_detector_stats_service_all on public.intelligence_detector_stats;
create policy intelligence_detector_stats_service_all
    on public.intelligence_detector_stats
    for all
    to service_role
    using (true)
    with check (true);
