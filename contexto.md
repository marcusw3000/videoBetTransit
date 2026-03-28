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
  - pode fazer proxy do MJPEG e do health do Python
  - publica atualizacoes via SignalR

Frontend React
  - consome REST e SignalR do backend
  - exibe o feed MJPEG anotado vindo do Python
  - mostra contador, timer, faixas, historico filtravel, painel operacional e alertas de monitoramento
```

Fluxo resumido:
1. `app.py` le o stream configurado em `config.json`.
2. A engine detecta e rastreia veiculos dentro da ROI.
3. Quando um veiculo cruza a linha, a engine envia `POST /api/rounds/count-events` para o backend.
4. O backend atualiza o round e faz broadcast via SignalR.
5. O frontend atualiza contador, timer, historico e lista de deteccoes.
6. O video mostrado no browser pode vir do proxy `http://localhost:5000/proxy/video-feed`, que encaminha para o MJPEG Python ja anotado.
7. O painel operacional consulta `http://localhost:5000/proxy/health` para mostrar estado da camera, backend e metricas.
8. A UI gera alertas quando stream, backend, frames ou contagem entram em estado suspeito.
9. A secao de historico permite filtrar por camera, periodo e ID do round, alem de exportar CSV de rounds e count-events.

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
Para validar o projeto inteiro de uma vez, use `validate.bat` na raiz.

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
- `validate.bat`: validacao unica com sintaxe Python, testes Python, testes .NET e build do frontend.
- `traffic-counter-front/src/App.jsx`: orquestra tela principal.
- `traffic-counter-front/src/components/VideoPlayer.jsx`: exibe o feed MJPEG anotado.

## Engine Python

Responsabilidades principais:
- abrir o stream com reconexao automatica
- rodar YOLO e tracker
- filtrar por ROI
- contar cruzamento da linha
- permitir calibrar ROI e linha por arraste na propria janela Python
- salvar snapshots opcionais
- enviar `count-events` e `live-detections`
- servir `/health` e `/video_feed` via Flask, publicados por `waitress`
- enfileirar envios HTTP com workers fixos e descarte controlado quando o backend atrasar

Configuracoes relevantes em `config.json`:
- `stream_url`: URL do stream da camera
- `model`: arquivo do modelo YOLO
- `tracker`: arquivo do tracker
- `api_key`: chave usada para falar com o backend protegido
- `mjpeg_token`: token exigido pelo endpoint MJPEG
- `imgsz`: tamanho de inferencia do YOLO
- `roi`: regiao de interesse
- `line`: linha de contagem
- `line_dead_zone_px`: banda de seguranca em torno da linha para reduzir dupla contagem por oscilacao
- `count_direction`: `up`, `down` ou `any`
- `show_window`: mostra janela OpenCV local
- `save_snapshots`: salva recortes dos veiculos contados
- `mjpeg_host`: host do servidor MJPEG
- `mjpeg_port`: porta do servidor MJPEG
- `class_thresholds`: thresholds especificos por classe para area minima, hits minimos e confianca minima

Observacao importante:
- o browser nao desenha mais overlay separado sobre HLS
- o frame anotado sai pronto do Python
- isso evita o atraso visual entre video e boxes
- o feed MJPEG pode exigir `token` na query string
- a criacao da app MJPEG foi isolada em funcao propria para facilitar evolucao de deploy
- a calibracao operacional de ROI e linha agora acontece no proprio Python, com janela OpenCV e painel de botoes
- `count-events` usa backlog curto com descarte explicito quando a fila enche
- `live-detections` prioriza o frame mais recente quando a fila satura
- a calibracao de deteccao agora aceita thresholds por classe e zona morta perto da linha

## Backend .NET

Principais rotas:
- `GET /api/rounds/current`
- `GET /api/rounds/history`
- `GET /api/rounds/{roundId}/count-events`
- `POST /api/rounds/settle`
- `POST /api/rounds/count-events`
- `GET /api/camera-config/{cameraId}`
- `POST /api/camera-config/{cameraId}`
- `GET /proxy/video-feed`
- `GET /proxy/health`

Eventos SignalR:
- `count_updated`
- `round_settled`

Caracteristicas atuais:
- persistencia local em SQLite via EF Core
- migracao inicial versionada em `TrafficCounter.Api/Migrations`
- rounds com encerramento automatico
- rotas sensiveis protegidas por API key
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
4. mostra o feed MJPEG em `VideoPlayer`
5. mostra a lista de deteccoes recebida por SignalR
6. consulta o health operacional para exibir status da camera, backend, feed MJPEG, FPS e ultimo evento

Observacao:
- `VideoPlayer.jsx` usa `<img>` apontando para o feed MJPEG
- `OperationsCard.jsx` mostra saude operacional usando o health proxied do backend
- `AlertsPanel.jsx` mostra alertas para stream indisponivel, backend com falha, frames parados e contagem zerada suspeita
- o historico usa `GET /api/rounds/history` e `GET /api/rounds/{roundId}/count-events` para filtros, tendencia e exportacao CSV
- por padrao, `VITE_MJPEG_URL` aponta para o proxy do backend
- por padrao, `VITE_MJPEG_HEALTH_URL` aponta para `http://localhost:5000/proxy/health`
- o frontend nao possui mais tela de configuracao de ROI/linha
- `VITE_API_BASE_URL`, `VITE_SIGNALR_BASE_URL` e `VITE_MJPEG_URL` devem ser definidos por ambiente
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
- o token do MJPEG pode ficar restrito ao backend quando o proxy `/proxy/video-feed` e usado

## Topologia de Deploy Recomendada

Topologia alvo:
- `Edge publica`: dominio HTTPS unico, com WAF/reverse proxy
- `Frontend React`: servido como build estatico atras da mesma borda publica
- `Backend .NET`: exposto apenas pela borda publica, servindo API, SignalR e proxy do MJPEG
- `Engine Python`: acessivel apenas na rede interna, sem exposicao publica direta
- `Banco`: acessivel apenas pela API .NET
- `Storage de snapshots`: preferencialmente externo ao disco local em producao

Fluxo recomendado:
1. o navegador acessa apenas o dominio HTTPS publico
2. o frontend fala apenas com o backend .NET no mesmo host logico
3. o MJPEG no navegador entra apenas por `GET /proxy/video-feed`
4. o backend .NET busca `http://python-engine-interna:8090/video_feed` internamente
5. a engine Python envia `count-events` e `live-detections` apenas para a API interna/publicada do backend

Regras praticas:
- nao expor `8090` publicamente em producao
- nao apontar o frontend para a engine Python diretamente em producao
- concentrar TLS, CORS e rate limiting na borda publica
- manter a engine Python em rede privada e com firewall restritivo
- deixar SignalR, API REST e proxy MJPEG sob o mesmo dominio da aplicacao

Exemplo de distribuicao:
- `https://jogo.exemplo.com/` -> frontend React
- `https://jogo.exemplo.com/api/*` -> backend .NET
- `https://jogo.exemplo.com/hubs/*` -> SignalR .NET
- `https://jogo.exemplo.com/proxy/video-feed` -> proxy MJPEG .NET
- `http://python-engine-interna:8090/*` -> engine Python, somente rede privada

## Portas e Endpoints Locais

- Backend .NET: `http://localhost:5000`
- Frontend Vite: `http://localhost:5173`
- Proxy MJPEG .NET: `http://localhost:5000/proxy/video-feed`
- Proxy Health .NET: `http://localhost:5000/proxy/health`
- MJPEG Python: `http://127.0.0.1:8090/video_feed`
- Health Python: `http://127.0.0.1:8090/health`

## Pontos de Atencao

- O backend grava `trafficcounter.db`, entao rounds, count-events e camera-config sobrevivem a reinicios.
- Se `BackendApiKey`, `api_key`, `VITE_BACKEND_API_KEY` e `mjpeg_token` estiverem divergentes, o sistema vai aparentar falha de integracao mesmo com os servicos no ar.
- O uso do proxy `/proxy/video-feed` reduz o problema de mixed content e evita expor o token do MJPEG no browser por padrao.
- A `.venv` precisa estar atualizada com `requirements.txt`.
- Clicar no terminal do Windows em modo QuickEdit pode congelar temporariamente a engine Python.
