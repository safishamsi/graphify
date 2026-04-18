-- depOS: repositories table + RLS (members read, admins write).

create table if not exists public.repositories (
    id uuid primary key default gen_random_uuid(),
    org_id uuid not null references public.organizations (id) on delete cascade,
    slug text not null,
    enabled_for_analysis boolean not null default true,
    include_in_federated boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (org_id, slug)
);

create index if not exists repositories_org_idx on public.repositories (org_id);
create index if not exists repositories_slug_idx on public.repositories (slug);

alter table public.repositories enable row level security;

drop policy if exists repositories_member_select on public.repositories;
create policy repositories_member_select
    on public.repositories
    for select
    to authenticated
    using (public.is_org_member(org_id));

drop policy if exists repositories_admin_insert on public.repositories;
create policy repositories_admin_insert
    on public.repositories
    for insert
    to authenticated
    with check (public.is_org_admin(org_id));

drop policy if exists repositories_admin_update on public.repositories;
create policy repositories_admin_update
    on public.repositories
    for update
    to authenticated
    using (public.is_org_admin(org_id))
    with check (public.is_org_admin(org_id));

drop policy if exists repositories_admin_delete on public.repositories;
create policy repositories_admin_delete
    on public.repositories
    for delete
    to authenticated
    using (public.is_org_admin(org_id));

drop policy if exists repositories_service_all on public.repositories;
create policy repositories_service_all
    on public.repositories
    for all
    to service_role
    using (true)
    with check (true);

-- Keep updated_at fresh.
create or replace function public.touch_updated_at()
returns trigger
language plpgsql
as $$
begin
    new.updated_at := now();
    return new;
end;
$$;

drop trigger if exists repositories_touch_updated_at on public.repositories;
create trigger repositories_touch_updated_at
    before update on public.repositories
    for each row execute function public.touch_updated_at();
