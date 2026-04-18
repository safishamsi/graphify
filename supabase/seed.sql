-- Local-dev seed for depOS. DO NOT run in production.
-- Creates a demo org and two demo repos so the UI has something to render
-- before a user signs up. Organization_members is intentionally empty so
-- signup + first-login flows exercise trigger-based membership creation.

insert into public.organizations (slug, name)
values ('demo-org', 'Demo Organization')
on conflict (slug) do nothing;

insert into public.repositories (org_id, slug)
select o.id, slug
from public.organizations o
cross join (values ('demo/depos-web'), ('demo/depos-api')) as v(slug)
where o.slug = 'demo-org'
on conflict (org_id, slug) do nothing;
