create extension if not exists pgcrypto;

create table if not exists public.stream_profiles (
  scope text not null default 'videoBetTransit',
  id text not null,
  name text not null default '',
  stream_url text not null,
  camera_id text not null default '',
  roi jsonb not null default '{}'::jsonb,
  line jsonb not null default '{}'::jsonb,
  count_direction text not null default 'any',
  is_selected boolean not null default false,
  updated_at timestamptz not null default timezone('utc', now()),
  created_at timestamptz not null default timezone('utc', now()),
  constraint stream_profiles_pkey primary key (scope, id)
);

create index if not exists stream_profiles_scope_updated_idx
  on public.stream_profiles (scope, updated_at desc);

create or replace function public.set_stream_profiles_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = timezone('utc', now());
  return new;
end;
$$;

drop trigger if exists stream_profiles_set_updated_at on public.stream_profiles;

create trigger stream_profiles_set_updated_at
before update on public.stream_profiles
for each row
execute function public.set_stream_profiles_updated_at();

alter table public.stream_profiles enable row level security;

drop policy if exists "service role full access stream_profiles" on public.stream_profiles;

create policy "service role full access stream_profiles"
on public.stream_profiles
for all
to service_role
using (true)
with check (true);
