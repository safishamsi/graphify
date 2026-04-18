-- Private bucket for graph JSON blobs (access via signed URLs + service role).

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values (
    'graph-snapshots',
    'graph-snapshots',
    false,
    52428800,
    array['application/json']::text[]
)
on conflict (id) do nothing;
