# Supabase Setup

## Objetivo

Usar o Supabase como banco PostgreSQL oficial do backend, mantendo:

- `frontend` e `vision-worker` falando apenas com a API .NET
- `backend` como dono do schema e das migrations
- Supabase como banco gerenciado, nao como substituto da API

## Arquivos envolvidos

- [appsettings.json](/c:/Users/Marcus/Desktop/projetos/videoBetTransit/backend/TrafficCounter.Api/appsettings.json)
- [appsettings.Development.json](/c:/Users/Marcus/Desktop/projetos/videoBetTransit/backend/TrafficCounter.Api/appsettings.Development.json)
- [AppDbContextFactory.cs](/c:/Users/Marcus/Desktop/projetos/videoBetTransit/backend/TrafficCounter.Api/Data/AppDbContextFactory.cs)
- [docker-compose.supabase.yml](/c:/Users/Marcus/Desktop/projetos/videoBetTransit/infra/docker-compose.supabase.yml)
- [.env.supabase.example](/c:/Users/Marcus/Desktop/projetos/videoBetTransit/.env.supabase.example)
- [supabase_round_core.sql](/c:/Users/Marcus/Desktop/projetos/videoBetTransit/supabase_round_core.sql)
- [supabase_stream_profiles.sql](/c:/Users/Marcus/Desktop/projetos/videoBetTransit/supabase_stream_profiles.sql)
- [supabase_stream_schedule_rules.sql](/c:/Users/Marcus/Desktop/projetos/videoBetTransit/supabase_stream_schedule_rules.sql)

## Modo de operacao

- `Development`: usa SQLite local por padrao
- `Production/Homologacao`: usa `ConnectionStrings__DefaultConnection`
- `dotnet ef`: usa a mesma resolucao de config do backend e aceita override por env var

## Passo a passo

1. Copie [.env.supabase.example](/c:/Users/Marcus/Desktop/projetos/videoBetTransit/.env.supabase.example) para um arquivo `.env`.
2. Preencha `SUPABASE_DB_URL` com a connection string do banco Postgres do projeto Supabase.
3. Preencha `SUPABASE_URL` e `SUPABASE_SERVICE_KEY` para sincronizacao do worker.
4. Defina `BACKEND_API_KEY`.
5. Aplique as migrations:

```powershell
$env:ConnectionStrings__DefaultConnection="Host=db.YOUR_PROJECT_REF.supabase.co;Port=5432;Database=postgres;Username=postgres;Password=YOUR_DB_PASSWORD;SSL Mode=Require;Trust Server Certificate=true"
cd backend\TrafficCounter.Api
dotnet ef database update
```

6. Se precisar bootstrap manual do schema operacional no painel SQL do Supabase, execute os arquivos nesta ordem:

- `supabase_round_core.sql`
- `supabase_stream_profiles.sql`
- `supabase_stream_schedule_rules.sql`

7. Suba a stack com compose dedicado:

```powershell
cd infra
docker compose -f docker-compose.supabase.yml --env-file ..\.env up --build
```

## Observacoes

- o backend continua sendo a fonte oficial de `rounds`, `round_markets`, `round_events` e `vehicle_crossing_events`
- o frontend nao deve acessar tabelas do Supabase diretamente
- o worker continua enviando eventos para o backend, nunca direto para o banco
- o worker aceita `BACKEND_URL`, `BACKEND_API_KEY`, `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `CAMERA_ID` e `LINE_ID` por ambiente
- se quiser usar Supabase em dev local sem Docker, basta exportar `ConnectionStrings__DefaultConnection` antes do `dotnet run`
- `supabase_round_core.sql` agora usa os mesmos nomes fisicos do EF/Npgsql para evitar drift com migrations:
  - `Round` -> `Rounds`
  - `RoundMarket` -> `RoundMarkets`
  - `RoundEvent` -> `RoundEvents`
  - `VehicleCrossingEvent` -> `VehicleCrossingEvents`
- o escopo atual do SQL do core nao inclui tabelas legadas de stream como `camera_sources`, `stream_sessions`, `recording_segments` e `stream_health_logs`
- o acesso inicial do core no Supabase e `backend only`, com RLS habilitado e policy apenas para `service_role`
- `VehicleCrossingEvents.SessionId` permanece opcional; o SQL cria a FK para `StreamSessions` somente se essa tabela ja existir no banco

## Conexao recomendada

Use a string com SSL:

```text
Host=db.YOUR_PROJECT_REF.supabase.co;Port=5432;Database=postgres;Username=postgres;Password=YOUR_DB_PASSWORD;SSL Mode=Require;Trust Server Certificate=true
```

## Rollback

Se quiser voltar para dev local:

- remova `ConnectionStrings__DefaultConnection` do ambiente
- rode o backend em `ASPNETCORE_ENVIRONMENT=Development`
- ele volta a usar `Data Source=trafficcounter.db`
