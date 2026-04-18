-- depOS: organizations table.
-- RLS-first: members of the org can read; owners/admins can write.

create extension if not exists "pgcrypto";

create table if not exists public.organizations (
    id uuid primary key default gen_random_uuid(),
    slug text unique not null,
    name text not null default '',
    created_at timestamptz not null default now()
);

create index if not exists organizations_slug_idx on public.organizations (slug);

alter table public.organizations enable row level security;

-- Membership check is defined in the organization_members migration (next file).
-- For now, only authenticated service-role requests bypass these policies;
-- all policy bodies referencing organization_members are installed there to
-- avoid a circular dependency on a not-yet-created table.

drop policy if exists organizations_owner_insert on public.organizations;
create policy organizations_owner_insert
    on public.organizations
    for insert
    to authenticated
    with check (true);
-- New orgs can be created by any authenticated user; they become owner via
-- the organization_members migration which auto-inserts an owner row.

drop policy if exists organizations_service_all on public.organizations;
create policy organizations_service_all
    on public.organizations
    for all
    to service_role
    using (true)
    with check (true);
