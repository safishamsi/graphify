-- depOS: ci_signals table (post-CI correlation rows).

create table if not exists public.ci_signals (
    id bigint generated always as identity primary key,
    org_id uuid references public.organizations (id) on delete cascade,
    repo_slug text not null,
    head_sha text not null,
    check_conclusion text not null default '',
    predicted_files jsonb not null default '[]'::jsonb,
    overlap_score double precision not null default 0.0,
    created_at timestamptz not null default now()
);

create index if not exists ci_signals_repo_head_idx
    on public.ci_signals (repo_slug, head_sha);
create index if not exists ci_signals_org_idx on public.ci_signals (org_id);

alter table public.ci_signals enable row level security;

-- Anonymous reads are intentionally blocked. Members of the owning org see
-- their signals; service_role (FastAPI backend) bypasses.
drop policy if exists ci_signals_member_select on public.ci_signals;
create policy ci_signals_member_select
    on public.ci_signals
    for select
    to authenticated
    using (org_id is null or public.is_org_member(org_id));

drop policy if exists ci_signals_service_all on public.ci_signals;
create policy ci_signals_service_all
    on public.ci_signals
    for all
    to service_role
    using (true)
    with check (true);
