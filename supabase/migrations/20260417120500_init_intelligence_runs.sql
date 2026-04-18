-- depOS: intelligence_runs and intelligence_findings — the storage surface
-- for Modules 1–7 output so the Next.js UI can read confirmed/gray-zone
-- findings via Supabase client directly (RLS enforced).

create table if not exists public.intelligence_runs (
    id uuid primary key default gen_random_uuid(),
    org_id uuid not null references public.organizations (id) on delete cascade,
    repo_slug text not null,
    base_ref text,
    head_ref text,
    analysis_mode text not null check (analysis_mode in ('diff_aware', 'full_repo_scan')),
    provider text,
    low_stitcher_coverage boolean not null default false,
    token_estimator text not null default 'chars4',
    ranking_phase integer not null default 0,
    status text not null default 'running' check (status in ('running', 'succeeded', 'partial_reasoning', 'failed')),
    pack_manifest_id text,
    started_at timestamptz not null default now(),
    finished_at timestamptz
);

create index if not exists intelligence_runs_org_repo_idx
    on public.intelligence_runs (org_id, repo_slug, started_at desc);

alter table public.intelligence_runs enable row level security;

drop policy if exists intelligence_runs_member_select on public.intelligence_runs;
create policy intelligence_runs_member_select
    on public.intelligence_runs
    for select
    to authenticated
    using (public.is_org_member(org_id));

drop policy if exists intelligence_runs_service_all on public.intelligence_runs;
create policy intelligence_runs_service_all
    on public.intelligence_runs
    for all
    to service_role
    using (true)
    with check (true);

-- intelligence_findings: one row per surfaced finding.
create table if not exists public.intelligence_findings (
    id uuid primary key default gen_random_uuid(),
    run_id uuid not null references public.intelligence_runs (id) on delete cascade,
    trust_level text not null check (trust_level in ('confirmed', 'partially_confirmed', 'evaluator_surfaced')),
    mode text not null check (mode in ('A', 'B', 'C')),
    bug_type text not null default '',
    description text not null default '',
    affected_components jsonb not null default '[]'::jsonb,
    witness_path jsonb not null default '[]'::jsonb,
    missing_guard text,
    recommended_fix text,
    reasoner_confidence double precision not null default 0.0,
    ranking_phase integer not null default 0,
    verifier_outcome text not null default '',
    verifier_checks_passed jsonb not null default '[]'::jsonb,
    verifier_checks_inconclusive jsonb not null default '[]'::jsonb,
    rls_verdict text,
    migration_state_facts jsonb not null default '{}'::jsonb,
    caveats jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create index if not exists intelligence_findings_run_idx
    on public.intelligence_findings (run_id);
create index if not exists intelligence_findings_trust_idx
    on public.intelligence_findings (trust_level);

alter table public.intelligence_findings enable row level security;

-- Read via join on intelligence_runs.org_id.
drop policy if exists intelligence_findings_member_select on public.intelligence_findings;
create policy intelligence_findings_member_select
    on public.intelligence_findings
    for select
    to authenticated
    using (
        exists (
            select 1
            from public.intelligence_runs r
            where r.id = intelligence_findings.run_id
              and public.is_org_member(r.org_id)
        )
    );

drop policy if exists intelligence_findings_service_all on public.intelligence_findings;
create policy intelligence_findings_service_all
    on public.intelligence_findings
    for all
    to service_role
    using (true)
    with check (true);
