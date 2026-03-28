# contexto.md - videoBetTransit

Sistema de contagem de veiculos em tempo real com mercado de apostas por faixas de contagem. O projeto roda em tres processos principais: engine Python, backend .NET e frontend React.

## Arquitetura Geral

```text
Python app.py
  - consome o stream de camera
  - roda YOLO + tracking + contagem
  - envia eventos HTTP para o backend
  - publica video anotado via MJPEG com Flask + waitress

Backend .NET 8
  - persiste round atual, historico, count-events e camera-config em SQLite
  - recebe count-events da engine
  - protege rotas sensiveis com `X-API-Key`
  - publica atualizacoes via SignalR

Frontend React
  - consome REST e SignalR do backend
  - exibe o feed MJPEG anotado vindo do Python
  - envia API key nas acoes administrativas
  - mostra contador, timer, faixas e historico
```

Fluxo resumido:
1. `app.py` le o stream configurado em `config.json`.
2. A engine detecta e rastreia veiculos dentro da ROI.
3. Quando um veiculo cruza a linha, a engine envia `POST /api/rounds/count-events` para o backend.
4. O backend atualiza o round e faz broadcast via SignalR.
5. O frontend atualiza contador, timer, historico e lista de deteccoes.
6. O video mostrado no browser vem do endpoint MJPEG `http://127.0.0.1:8090/video_feed`, ja com boxes desenhadas no Python.

## Como Rodar

Todos os comandos partem da raiz do repositorio.

```bash
# Backend .NET
cd TrafficCounter.Api
dotnet run

# Frontend React
cd traffic-counter-front
npm run dev

# Engine Python
python app.py
```

No Windows, `start.bat` sobe tudo e ainda garante a instalacao das dependencias Python antes de iniciar a engine.
No ambiente local, o `start.bat` tambem sobe o backend com `ASPNETCORE_ENVIRONMENT=Development`.

## Estrutura de Pastas

```text
videoBetTransit/
|-- app.py
|-- backend_client.py
|-- config.json
|-- requirements.txt
|-- start.bat
|-- snapshots/
|-- TrafficCounter.Api/
|-- traffic-counter-front/
```

Arquivos importantes:
- `app.py`: engine de deteccao, contagem e servidor MJPEG.
- `backend_client.py`: cliente HTTP usado pela engine para falar com o backend.
- `config.json`: stream, ROI, linha de contagem, modelo, MJPEG host e porta.
- `start.bat`: inicializacao automatica do backend, frontend e engine.
- `traffic-counter-front/src/App.jsx`: orquestra tela principal.
- `traffic-counter-front/src/components/VideoPlayer.jsx`: exibe o feed MJPEG anotado.

## Engine Python

Responsabilidades principais:
- abrir o stream com reconexao automatica
- rodar YOLO e tracker
- filtrar por ROI
- contar cruzamento da linha
- salvar snapshots opcionais
- enviar `count-events` e `live-detections`
- servir `/health` e `/video_feed` via Flask, publicados por `waitress`

Configuracoes relevantes em `config.json`:
- `stream_url`: URL do stream da camera
- `model`: arquivo do modelo YOLO
- `tracker`: arquivo do tracker
- `api_key`: chave usada para falar com o backend protegido
- `mjpeg_token`: token exigido pelo endpoint MJPEG
- `roi`: regiao de interesse
- `line`: linha de contagem
- `count_direction`: `up`, `down` ou `any`
- `show_window`: mostra janela OpenCV local
- `save_snapshots`: salva recortes dos veiculos contados
- `mjpeg_host`: host do servidor MJPEG
- `mjpeg_port`: porta do servidor MJPEG

Observacao importante:
- o browser nao desenha mais overlay separado sobre HLS
- o frame anotado sai pronto do Python
- isso evita o atraso visual entre video e boxes
- o feed MJPEG pode exigir `token` na query string
- a criacao da app MJPEG foi isolada em funcao propria para facilitar evolucao de deploy

## Backend .NET

Principais rotas:
- `GET /api/rounds/current`
- `GET /api/rounds/history`
- `GET /api/rounds/{roundId}/count-events`
- `POST /api/rounds/settle`
- `POST /api/rounds/count-events`
- `GET /api/camera-config/{cameraId}`
- `POST /api/camera-config/{cameraId}`

Eventos SignalR:
- `count_updated`
- `round_settled`

Caracteristicas atuais:
- persistencia local em SQLite via EF Core
- migracao inicial versionada em `TrafficCounter.Api/Migrations`
- rounds com encerramento automatico
- rotas sensiveis protegidas por API key
- CORS configurado por ambiente via `Cors:AllowedOrigins`

## Frontend React

Tecnologias principais:
- React + Vite
- Axios
- SignalR

Fluxo atual:
1. busca o round atual
2. busca o historico
3. conecta nos hubs SignalR
4. mostra o feed MJPEG em `VideoPlayer`
5. mostra a lista de deteccoes recebida por SignalR

Observacao:
- `VideoPlayer.jsx` usa `<img>` apontando para o feed MJPEG
- a tela de configuracao tambem usa preview MJPEG
- `VITE_BACKEND_API_KEY` protege chamadas administrativas do frontend
- `VITE_MJPEG_TOKEN` e anexado ao feed no browser
- `VITE_API_BASE_URL`, `VITE_SIGNALR_BASE_URL`, `VITE_BACKEND_API_KEY`, `VITE_MJPEG_URL` e `VITE_MJPEG_TOKEN` devem ser definidos por ambiente
- `hls.js` foi removido do fluxo principal

## Ambientes

Backend .NET:
- `TrafficCounter.Api/appsettings.json`: base local atual
- `TrafficCounter.Api/appsettings.Development.json.example`: exemplo para desenvolvimento
- `TrafficCounter.Api/appsettings.Production.json.example`: exemplo para producao

Frontend React:
- `traffic-counter-front/.env.example`: exemplo generico
- `traffic-counter-front/.env.development.example`: exemplo para desenvolvimento
- `traffic-counter-front/.env.production.example`: exemplo para producao

Observacao:
- em producao, `Cors:AllowedOrigins` deve ser definido explicitamente
- as chaves do backend e do MJPEG devem ser diferentes e fortes

## Portas e Endpoints Locais

- Backend .NET: `http://localhost:5000`
- Frontend Vite: `http://localhost:5173`
- MJPEG Python: `http://127.0.0.1:8090/video_feed`
- Health Python: `http://127.0.0.1:8090/health`

## Pontos de Atencao

- O backend grava `trafficcounter.db`, entao rounds, count-events e camera-config sobrevivem a reinicios.
- Se `BackendApiKey`, `api_key`, `VITE_BACKEND_API_KEY` e `mjpeg_token` estiverem divergentes, o sistema vai aparentar falha de integracao mesmo com os servicos no ar.
- Se o frontend estiver em HTTPS e o MJPEG em HTTP, pode haver bloqueio por mixed content.
- A `.venv` precisa estar atualizada com `requirements.txt`.
- Clicar no terminal do Windows em modo QuickEdit pode congelar temporariamente a engine Python.
