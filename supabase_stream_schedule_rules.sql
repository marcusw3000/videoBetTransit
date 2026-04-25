create extension if not exists pgcrypto;

create table if not exists public.stream_schedule_rules (
  scope text not null default 'videoBetTransit',
  id text not null,
  name text not null default '',
  enabled boolean not null default true,
  start_time text not null,
  end_time text not null,
  allowed_profile_ids jsonb not null default '[]'::jsonb,
  timezone text not null default 'America/Sao_Paulo',
  updated_at timestamptz not null default timezone('utc', now()),
  created_at timestamptz not null default timezone('utc', now()),
  constraint stream_schedule_rules_pkey primary key (scope, id)
);

create index if not exists stream_schedule_rules_scope_updated_idx
  on public.stream_schedule_rules (scope, updated_at desc);

create or replace function public.set_stream_schedule_rules_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = timezone('utc', now());
  return new;
end;
$$;

drop trigger if exists stream_schedule_rules_set_updated_at on public.stream_schedule_rules;

create trigger stream_schedule_rules_set_updated_at
before update on public.stream_schedule_rules
for each row
execute function public.set_stream_schedule_rules_updated_at();

alter table public.stream_schedule_rules enable row level security;

drop policy if exists "service role full access stream_schedule_rules" on public.stream_schedule_rules;

create policy "service role full access stream_schedule_rules"
on public.stream_schedule_rules
for all
to service_role
using (true)
with check (true);
