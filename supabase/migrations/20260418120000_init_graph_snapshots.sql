-- depOS: graph_snapshots — metadata for node-link JSON blobs in Supabase Storage.

create table if not exists public.graph_snapshots (
    id uuid primary key default gen_random_uuid(),
    org_id uuid not null references public.organizations (id) on delete cascade,
    repo_slug text not null,
    git_sha text not null,
    storage_path text not null,
    status text not null default 'pending'
        check (status in ('pending', 'ready', 'failed')),
    byte_size bigint,
    content_sha256 text,
    created_by uuid,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists graph_snapshots_org_repo_sha_idx
    on public.graph_snapshots (org_id, repo_slug, git_sha desc);

create unique index if not exists graph_snapshots_storage_path_uidx
    on public.graph_snapshots (storage_path);

alter table public.graph_snapshots enable row level security;

drop policy if exists graph_snapshots_member_select on public.graph_snapshots;
create policy graph_snapshots_member_select
    on public.graph_snapshots
    for select
    to authenticated
    using (public.is_org_member(org_id));

drop policy if exists graph_snapshots_service_all on public.graph_snapshots;
create policy graph_snapshots_service_all
    on public.graph_snapshots
    for all
    to service_role
    using (true)
    with check (true);

-- Optional linkage from CI correlation rows to a graph snapshot.
alter table public.ci_signals
    add column if not exists graph_snapshot_id uuid references public.graph_snapshots (id) on delete set null;

create index if not exists ci_signals_graph_snapshot_idx
    on public.ci_signals (graph_snapshot_id);
