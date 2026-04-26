create extension if not exists pgcrypto;

create table if not exists public."Rounds" (
  "RoundId" uuid not null,
  "CameraId" character varying(128) not null,
  "RoundMode" character varying(32) not null,
  "Status" character varying(32) not null,
  "DisplayName" character varying(128) not null,
  "CreatedAt" timestamp with time zone not null,
  "BetCloseAt" timestamp with time zone not null,
  "EndsAt" timestamp with time zone not null,
  "SettledAt" timestamp with time zone null,
  "CurrentCount" integer not null,
  "FinalCount" integer null,
  "VoidedAt" timestamp with time zone null,
  "VoidReason" character varying(512) null,
  constraint "PK_Rounds" primary key ("RoundId")
);

create index if not exists "IX_Rounds_Status"
  on public."Rounds" ("Status");

create index if not exists "IX_Rounds_CreatedAt"
  on public."Rounds" ("CreatedAt");

create index if not exists "IX_Rounds_CameraId_Status"
  on public."Rounds" ("CameraId", "Status");

create table if not exists public."RoundMarkets" (
  "MarketId" uuid not null,
  "RoundId" uuid not null,
  "MarketType" character varying(16) not null,
  "Label" character varying(128) not null,
  "Odds" numeric(10,4) not null,
  "Threshold" integer null,
  "Min" integer null,
  "Max" integer null,
  "TargetValue" integer null,
  "IsWinner" boolean null,
  "SortOrder" integer not null,
  constraint "PK_RoundMarkets" primary key ("MarketId"),
  constraint "FK_RoundMarkets_Rounds_RoundId"
    foreign key ("RoundId")
    references public."Rounds" ("RoundId")
    on delete cascade
);

create index if not exists "IX_RoundMarkets_RoundId"
  on public."RoundMarkets" ("RoundId");

create table if not exists public."RoundEvents" (
  "Id" uuid not null,
  "RoundId" uuid not null,
  "EventType" character varying(64) not null,
  "RoundStatus" character varying(32) not null,
  "TimestampUtc" timestamp with time zone not null,
  "CountValue" integer null,
  "Reason" character varying(512) null,
  "Source" character varying(64) null,
  constraint "PK_RoundEvents" primary key ("Id"),
  constraint "FK_RoundEvents_Rounds_RoundId"
    foreign key ("RoundId")
    references public."Rounds" ("RoundId")
    on delete cascade
);

create index if not exists "IX_RoundEvents_RoundId_TimestampUtc"
  on public."RoundEvents" ("RoundId", "TimestampUtc");

create index if not exists "IX_RoundEvents_RoundId_EventType"
  on public."RoundEvents" ("RoundId", "EventType");

create table if not exists public."VehicleCrossingEvents" (
  "Id" uuid not null,
  "RoundId" uuid null,
  "SessionId" uuid null,
  "CameraId" character varying(128) not null,
  "TimestampUtc" timestamp with time zone not null,
  "TrackId" bigint not null,
  "ObjectClass" character varying(32) not null,
  "Direction" character varying(32) not null,
  "LineId" character varying(64) not null,
  "FrameNumber" bigint not null,
  "Confidence" double precision not null,
  "SnapshotUrl" character varying(512) null,
  "Source" character varying(64) null,
  "StreamProfileId" character varying(128) null,
  "CountBefore" integer null,
  "CountAfter" integer null,
  "PreviousEventHash" character varying(128) null,
  "EventHash" character varying(128) not null,
  constraint "PK_VehicleCrossingEvents" primary key ("Id"),
  constraint "FK_VehicleCrossingEvents_Rounds_RoundId"
    foreign key ("RoundId")
    references public."Rounds" ("RoundId")
    on delete set null
);

create index if not exists "IX_VehicleCrossingEvents_RoundId"
  on public."VehicleCrossingEvents" ("RoundId");

create index if not exists "IX_VehicleCrossingEvents_RoundId_TimestampUtc"
  on public."VehicleCrossingEvents" ("RoundId", "TimestampUtc");

create index if not exists "IX_VehicleCrossingEvents_SessionId_TimestampUtc"
  on public."VehicleCrossingEvents" ("SessionId", "TimestampUtc");

create index if not exists "IX_VehicleCrossingEvents_EventHash"
  on public."VehicleCrossingEvents" ("EventHash");

do $$
begin
  if exists (
    select 1
    from information_schema.tables
    where table_schema = 'public'
      and table_name = 'StreamSessions'
  ) and not exists (
    select 1
    from information_schema.table_constraints
    where table_schema = 'public'
      and table_name = 'VehicleCrossingEvents'
      and constraint_name = 'FK_VehicleCrossingEvents_StreamSessions_SessionId'
  ) then
    alter table public."VehicleCrossingEvents"
      add constraint "FK_VehicleCrossingEvents_StreamSessions_SessionId"
      foreign key ("SessionId")
      references public."StreamSessions" ("Id")
      on delete set null;
  end if;
end
$$;

alter table public."Rounds" enable row level security;
alter table public."RoundMarkets" enable row level security;
alter table public."RoundEvents" enable row level security;
alter table public."VehicleCrossingEvents" enable row level security;

drop policy if exists "service role full access Rounds" on public."Rounds";
create policy "service role full access Rounds"
on public."Rounds"
for all
to service_role
using (true)
with check (true);

drop policy if exists "service role full access RoundMarkets" on public."RoundMarkets";
create policy "service role full access RoundMarkets"
on public."RoundMarkets"
for all
to service_role
using (true)
with check (true);

drop policy if exists "service role full access RoundEvents" on public."RoundEvents";
create policy "service role full access RoundEvents"
on public."RoundEvents"
for all
to service_role
using (true)
with check (true);

drop policy if exists "service role full access VehicleCrossingEvents" on public."VehicleCrossingEvents";
create policy "service role full access VehicleCrossingEvents"
on public."VehicleCrossingEvents"
for all
to service_role
using (true)
with check (true);
