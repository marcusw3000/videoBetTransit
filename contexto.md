# contexto.md - videoBetTransit

Sistema de contagem de veiculos em tempo real com mercado de apostas por faixas de contagem. O projeto roda em tres processos principais: worker Python, backend .NET e frontend React.

## Arquitetura Geral

```text
Python vision-worker/app.py
  - consome o stream de camera
  - roda YOLO + tracking + contagem
  - envia eventos HTTP para o backend
  - publica video anotado em `processed/<camera_id>` e fallback MJPEG com Flask + waitress

Backend .NET 8
  - persiste round atual, historico, count-events e camera-config em SQLite
  - recebe count-events da engine
  - protege rotas sensiveis com `X-API-Key`
  - pode fazer proxy do MJPEG e do health do Python
  - publica atualizacoes via SignalR

Frontend React
  - consome REST e SignalR do backend
  - exibe a live processada por camera via WebRTC/HLS, com fallback MJPEG
  - mostra contador, timer, faixas, historico filtravel, painel operacional e alertas de monitoramento
```

Fluxo resumido:
1. `vision-worker/app.py` le o stream configurado em `vision-worker/config.json`.
2. A engine detecta e rastreia veiculos dentro da ROI.
3. Quando um veiculo cruza a linha, a engine envia `POST /internal/round-count-event` para o backend.
4. O backend atualiza o round e faz broadcast via SignalR.
5. O frontend atualiza contador, timer, historico e lista de deteccoes.
6. O video mostrado no browser usa a saida `processed/<cameraId>` via MediaMTX, com fallback MJPEG direto do Python em `http://127.0.0.1:8090/video_feed`.
7. O painel operacional consulta o backend local e o `/health` do worker Python para mostrar estado da camera, backend e metricas.
8. A UI gera alertas quando stream, backend, frames ou contagem entram em estado suspeito.
9. A secao de historico permite filtrar por camera, periodo e ID do round, alem de exportar CSV de rounds e count-events.

## Como Rodar

Todos os comandos partem da raiz do repositorio.

```bash
# Backend .NET
backend-dev.bat

# Frontend React
frontend-dev.bat

# Worker Python oficial
vision-worker-dev.bat
```

No Windows, `start-dev.bat` e `start.bat dev` sobem backend, frontend e worker usando launchers dedicados.
Para validar o projeto inteiro de uma vez, use `validate.bat` na raiz.

## Estrutura de Pastas

```text
videoBetTransit/
|-- vision-worker/
|   |-- app.py
|   |-- backend_client.py
|   |-- config.json
|   |-- requirements.txt
|   |-- snapshots/
|-- start.bat
|-- start-dev.bat
|-- backend-dev.bat
|-- frontend-dev.bat
|-- vision-worker-dev.bat
|-- backend/
|-- frontend/
```

Arquivos importantes:
- `vision-worker/app.py`: worker oficial de deteccao, contagem e servidor MJPEG.
- `vision-worker/backend_client.py`: cliente HTTP usado pelo worker para falar com o backend.
- `vision-worker/config.json`: stream atual, esteira de presets, ROI, linha de contagem, rotacao, modelo, MJPEG host e porta.
- `backend-dev.bat`: launcher canonico do backend local.
- `frontend-dev.bat`: launcher canonico do frontend local.
- `vision-worker-dev.bat`: launcher canonico do worker local.
- `start.bat`: orquestrador principal da stack local.
- `start-dev.bat`: orquestrador simplificado para bootstrap local no Windows.
- `validate.bat`: validacao unica com sintaxe Python, testes Python, testes .NET e build do frontend.
- `frontend/src/App.jsx`: orquestra tela principal.
- `frontend/src/components/VideoPlayer.jsx`: exibe a live processada com fallback MJPEG.

## Engine Python

Responsabilidades principais:
- abrir o stream com reconexao automatica
- rodar YOLO e tracker
- filtrar por ROI
- contar cruzamento da linha
- permitir calibrar ROI e linha por arraste na propria janela Python
- manter uma esteira de presets com `camera_id`, URL, ROI, linha e direcao
- permitir rotacao randômica opcional entre presets, aplicada apenas em janela segura entre rounds
- salvar snapshots opcionais
- enviar `count-events` e `live-detections`
- servir `/health` e `/video_feed` via Flask, publicados por `waitress`
- contar apenas a classe `car`, ignorando `motorcycle`, `bus` e `truck`

Configuracoes relevantes em `vision-worker/config.json`:
- `stream_url`: URL do stream da camera
- `camera_id`: camera logica ativa, tambem usada para publicar em `processed/<camera_id>`
- `ffmpeg_capture_options`: opcoes de captura do FFmpeg via OpenCV, usadas para tentar reduzir buffer
- `stream_buffer_size`: tamanho do buffer da captura OpenCV
- `stream_open_timeout_ms`: timeout de abertura da captura
- `stream_read_timeout_ms`: timeout de leitura da captura
- `model`: arquivo do modelo YOLO
- `tracker`: arquivo do tracker
- `imgsz`: tamanho da inferencia, usado para equilibrar custo da engine e qualidade de deteccao
- `api_key`: chave usada para falar com o backend protegido
- `mjpeg_token`: token exigido pelo endpoint MJPEG
- `roi`: regiao de interesse
- `line`: linha de contagem
- `count_direction`: `up`, `down` ou `any`
- `stream_profiles`: esteira de presets operacionais; cada item carrega `id`, `name`, `stream_url`, `camera_id`, `roi`, `line` e `count_direction`
- `selected_stream_profile_id`: preset atualmente selecionado na esteira
- `stream_rotation.enabled`: ativa/desativa rotacao randômica; por padrao fica `false`
- `stream_rotation.mode`: modo da rotacao; hoje `round_boundary`
- `stream_rotation.strategy`: estrategia de sorteio; hoje `uniform_excluding_current`
- `show_window`: mostra janela OpenCV local
- `save_snapshots`: salva recortes dos veiculos contados
- `mjpeg_host`: host do servidor MJPEG
- `mjpeg_port`: porta do servidor MJPEG
- `supabase_url`: URL do projeto Supabase para sincronizacao opcional da esteira
- `supabase_service_key`: service role key usada pela engine para ler/escrever a esteira
- `supabase_stream_profiles_table`: nome da tabela remota, por padrao `stream_profiles`
- `supabase_stream_profiles_scope`: escopo logico para separar ambientes/projetos dentro da mesma tabela

Observacao importante:
- o browser nao desenha mais overlay separado sobre HLS
- o frame anotado sai pronto do Python
- isso evita o atraso visual entre video e boxes
- o feed MJPEG pode exigir `token` na query string
- a criacao da app MJPEG foi isolada em funcao propria para facilitar evolucao de deploy
- a calibracao operacional de ROI e linha agora acontece no proprio Python, com janela OpenCV e painel de botoes
- o painel local do Vision tambem permite informar `Camera ID`, abrir URL, salvar preset, ativar rotacao e sortear a proxima camera
- a esteira de streams continua salva localmente em `vision-worker/config.json` para garantir boot offline
- quando `supabase_url` e `supabase_service_key` estao configurados, a engine sincroniza a esteira com o Supabase
- no primeiro boot com Supabase, se a tabela remota estiver vazia, a configuracao local e publicada
- se ja existirem perfis remotos, eles passam a popular a esteira local
- a rotacao randômica fica pendente enquanto o round estiver `open` ou `closing`; a aplicacao so ocorre em `settling`, validada pelo backend
- o `/health` do worker expoe `selectedStreamProfileId` e `streamRotation`, alem dos dados de pipeline ja existentes
- a baseline atual de latencia ficou boa com:
  - `ffmpeg_capture_options`: `fflags;nobuffer|flags;low_delay|analyzeduration;0|probesize;32768`
  - `stream_buffer_size`: `1`
  - `imgsz`: `320`

## Backend .NET

Principais rotas:
- `GET /rounds/current`
- `GET /rounds/history`
- `GET /rounds/{roundId}/count-events`
- `GET /rounds/{roundId}/timeline`
- `POST /internal/round-count-event`
- `POST /internal/camera-config/validate-change`
- `POST /internal/rounds/profile-activated`
- `GET /internal/cameras/{cameraId}/round-lock`
- `GET /streams`
- `POST /streams`

Eventos SignalR:
- `count_updated`
- `round_settled`

Caracteristicas atuais:
- persistencia local em SQLite via EF Core
- migracao inicial versionada em `TrafficCounter.Api/Migrations`
- rounds com encerramento automatico
- rotas sensiveis protegidas por API key
- bloqueio operacional de alteracoes durante round `open`, `closing` e `settling`
- excecao interna `AllowSettling` para permitir rotacao controlada de camera apenas durante `settling`
- CORS configurado por ambiente via `Cors:AllowedOrigins`
- proxy opcional do MJPEG para unificar acesso pelo backend

## Frontend React

Tecnologias principais:
- React + Vite
- Axios
- SignalR

Fluxo atual:
1. busca o round atual
2. busca o historico
3. conecta nos hubs SignalR
4. monta a URL da live a partir do `cameraId` configurado
5. mostra o feed WebRTC/HLS com fallback MJPEG em `VideoPlayer`
6. mostra a lista de deteccoes recebida por SignalR
7. consulta o health operacional para exibir status da camera, backend, feed, FPS, perfil ativo e ultimo evento

Observacao:
- `VideoPlayer.jsx` nao foi alterado pela esteira randômica; ele continua consumindo a saida `processed/<cameraId>`
- `OperationsCard.jsx` mostra saude operacional via backend e health do worker
- `AlertsPanel.jsx` mostra alertas para stream indisponivel, backend com falha, frames parados e contagem zerada suspeita
- o historico usa `GET /rounds/history` e `GET /rounds/{roundId}/count-events` para filtros, tendencia e exportacao CSV
- por padrao, os endpoints locais do frontend apontam para `127.0.0.1`
- no Windows atual, o launcher `frontend-dev.bat` sobe o Vite com `--configLoader native` para contornar o erro local `spawn EPERM` do loader padrao
- o frontend nao possui mais tela de configuracao de ROI/linha
- o frontend tambem nao acompanha automaticamente a camera sorteada; para inspecionar outra saida, configure o `cameraId` correspondente
- `VITE_API_BASE_URL`, `VITE_SIGNALR_BASE_URL`, `VITE_HLS_BASE_URL`, `VITE_WEBRTC_BASE_URL`, `VITE_MJPEG_BASE_URL` e `VITE_MJPEG_TOKEN` devem ser definidos por ambiente quando necessario

Latencia:
- o `/health` do Python expõe tambem latencia interna basica da pipeline
- `lastPipelineMs` e `avgPipelineMs` representam o tempo entre a captura local do frame e a publicacao do frame anotado na memoria do MJPEG
- esses numeros ajudam a separar atraso interno da engine do atraso percebido da origem do stream
- a maior parte do atraso historico estava na captura/origem HLS; depois do tuning moderado e da reducao do `imgsz`, a stream anotada passou a ficar muito proxima da original

## Ambientes

Backend .NET:
- `TrafficCounter.Api/appsettings.json`: base local atual
- `TrafficCounter.Api/appsettings.Development.json.example`: exemplo para desenvolvimento
- `TrafficCounter.Api/appsettings.Production.json.example`: exemplo para producao

Frontend React:
- `frontend/` e a fonte principal da interface web
- `traffic-counter-front/` permanece apenas como referencia legada

Observacao:
- em producao, `Cors:AllowedOrigins` deve ser definido explicitamente
- as chaves do backend e do MJPEG devem ser diferentes e fortes
- o token do MJPEG pode ficar restrito ao backend quando o proxy `/proxy/video-feed` e usado

## Portas e Endpoints Locais

- Backend .NET: `http://127.0.0.1:8080`
- Frontend Vite: `http://127.0.0.1:5173`
- MJPEG Python: `http://127.0.0.1:8090/video_feed`
- Health Python: `http://127.0.0.1:8090/health`

## Pontos de Atencao

- O backend grava `trafficcounter.db`, entao rounds, count-events e camera-config sobrevivem a reinicios.
- Se `BackendApiKey`, `api_key`, `VITE_BACKEND_API_KEY` e `mjpeg_token` estiverem divergentes, o sistema vai aparentar falha de integracao mesmo com os servicos no ar.
- se quiser sincronizar a esteira no Supabase, crie a tabela usando [`supabase_stream_profiles.sql`](c:\Users\Marcus\Desktop\projetos\videoBetTransit\supabase_stream_profiles.sql) e configure `SUPABASE_URL` e `SUPABASE_SERVICE_KEY` no ambiente ou no `vision-worker/config.json`
- para rotação randômica real, cadastre ao menos dois `stream_profiles` com `camera_id` e URL validos
- cada preset publica na propria saida `processed/<camera_id>`; o frontend deve apontar para o `cameraId` que se quer monitorar
- troca manual de ROI, linha e stream profile segue bloqueada durante round ativo; a excecao `AllowSettling` e restrita a rotacao controlada durante `settling`
- No ambiente Windows atual, `127.0.0.1` e o host confiavel; `localhost` pode falhar por resolver em `::1`.
- A `.venv` precisa estar atualizada com `vision-worker/requirements.txt`.
- Clicar no terminal do Windows em modo QuickEdit pode congelar temporariamente a engine Python.
