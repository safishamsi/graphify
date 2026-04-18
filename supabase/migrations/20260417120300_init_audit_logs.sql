-- depOS: audit_logs table (append-only).

create table if not exists public.audit_logs (
    id bigint generated always as identity primary key,
    org_id uuid not null references public.organizations (id) on delete cascade,
    actor_user_id uuid references auth.users (id) on delete set null,
    action text not null,
    detail jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create index if not exists audit_logs_org_idx on public.audit_logs (org_id, created_at desc);
create index if not exists audit_logs_actor_idx on public.audit_logs (actor_user_id);

alter table public.audit_logs enable row level security;

drop policy if exists audit_logs_member_select on public.audit_logs;
create policy audit_logs_member_select
    on public.audit_logs
    for select
    to authenticated
    using (public.is_org_member(org_id));

-- No direct inserts/updates/deletes from authenticated clients.
-- Only service_role writes audit rows (via the FastAPI backend).
drop policy if exists audit_logs_service_all on public.audit_logs;
create policy audit_logs_service_all
    on public.audit_logs
    for all
    to service_role
    using (true)
    with check (true);
