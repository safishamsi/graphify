alter table public.organizations
    add column if not exists detector_policy jsonb not null default '{"enabled":[],"disabled":[],"severity_overrides":{}}'::jsonb;
