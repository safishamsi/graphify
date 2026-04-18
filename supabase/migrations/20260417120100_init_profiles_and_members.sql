-- depOS: profiles (one per auth.users) + organization_members (the table
-- acceptance test #2 targets for branch-aware schema reasoning).

create table if not exists public.profiles (
    id uuid primary key references auth.users on delete cascade,
    display_name text not null default '',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

alter table public.profiles enable row level security;

drop policy if exists profiles_self_select on public.profiles;
create policy profiles_self_select
    on public.profiles
    for select
    to authenticated
    using (id = auth.uid());

drop policy if exists profiles_self_update on public.profiles;
create policy profiles_self_update
    on public.profiles
    for update
    to authenticated
    using (id = auth.uid())
    with check (id = auth.uid());

drop policy if exists profiles_self_insert on public.profiles;
create policy profiles_self_insert
    on public.profiles
    for insert
    to authenticated
    with check (id = auth.uid());

drop policy if exists profiles_service_all on public.profiles;
create policy profiles_service_all
    on public.profiles
    for all
    to service_role
    using (true)
    with check (true);

-- Auto-create a profile row whenever a new auth.users row appears.
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
    insert into public.profiles (id, display_name)
    values (
        new.id,
        coalesce(new.raw_user_meta_data->>'display_name', split_part(new.email, '@', 1))
    )
    on conflict (id) do nothing;
    return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
    after insert on auth.users
    for each row execute function public.handle_new_user();

-- organization_members: composite PK, role enum-as-check.
create table if not exists public.organization_members (
    org_id uuid not null references public.organizations (id) on delete cascade,
    user_id uuid not null references auth.users (id) on delete cascade,
    role text not null default 'member' check (role in ('owner', 'admin', 'member')),
    created_at timestamptz not null default now(),
    primary key (org_id, user_id)
);

create index if not exists organization_members_user_idx
    on public.organization_members (user_id);

alter table public.organization_members enable row level security;

-- Helper: SECURITY DEFINER function avoids recursive RLS evaluation when
-- other tables' policies need to ask "is the caller a member of this org?".
create or replace function public.is_org_member(p_org_id uuid)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
    select exists (
        select 1
        from public.organization_members m
        where m.org_id = p_org_id
          and m.user_id = auth.uid()
    );
$$;

create or replace function public.is_org_admin(p_org_id uuid)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
    select exists (
        select 1
        from public.organization_members m
        where m.org_id = p_org_id
          and m.user_id = auth.uid()
          and m.role in ('owner', 'admin')
    );
$$;

grant execute on function public.is_org_member(uuid) to authenticated;
grant execute on function public.is_org_admin(uuid) to authenticated;

drop policy if exists organization_members_self_select on public.organization_members;
create policy organization_members_self_select
    on public.organization_members
    for select
    to authenticated
    using (user_id = auth.uid() or public.is_org_member(org_id));

drop policy if exists organization_members_admin_write on public.organization_members;
create policy organization_members_admin_write
    on public.organization_members
    for all
    to authenticated
    using (public.is_org_admin(org_id))
    with check (public.is_org_admin(org_id));

drop policy if exists organization_members_service_all on public.organization_members;
create policy organization_members_service_all
    on public.organization_members
    for all
    to service_role
    using (true)
    with check (true);

-- Now wire up read/write policies on organizations that depend on membership.
drop policy if exists organizations_member_select on public.organizations;
create policy organizations_member_select
    on public.organizations
    for select
    to authenticated
    using (public.is_org_member(id));

drop policy if exists organizations_admin_update on public.organizations;
create policy organizations_admin_update
    on public.organizations
    for update
    to authenticated
    using (public.is_org_admin(id))
    with check (public.is_org_admin(id));

drop policy if exists organizations_admin_delete on public.organizations;
create policy organizations_admin_delete
    on public.organizations
    for delete
    to authenticated
    using (public.is_org_admin(id));

-- Auto-grant owner role when an authenticated user creates an org.
create or replace function public.handle_new_organization()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
    if auth.uid() is not null then
        insert into public.organization_members (org_id, user_id, role)
        values (new.id, auth.uid(), 'owner')
        on conflict (org_id, user_id) do nothing;
    end if;
    return new;
end;
$$;

drop trigger if exists on_organization_created on public.organizations;
create trigger on_organization_created
    after insert on public.organizations
    for each row execute function public.handle_new_organization();
