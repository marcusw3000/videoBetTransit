# CLAUDE.md — videoBetTransit

Sistema de **contagem de veículos em tempo real** com mercado de apostas (odds por faixas de contagem). Três processos independentes se comunicam via HTTP e SignalR.

---

## Arquitetura Geral

```
┌─────────────────────┐      HTTP POST        ┌──────────────────────┐     SignalR      ┌──────────────────────┐
│  Engine Python       │  ─────────────────►   │  Backend .NET 8      │  ──────────────► │  Frontend React      │
│  (YOLOv8 + OpenCV)  │  /api/rounds/         │  (API REST + Hub)    │  ws://           │  (Vite + hls.js)     │
│  porta: nenhuma      │  count-events         │  porta: 5000         │  /hubs/round     │  porta: 5173         │
└─────────────────────┘                        └──────────────────────┘                  └──────────────────────┘
```

**Fluxo resumido:**
1. `app.py` lê um stream HLS, detecta veículos com YOLOv8 + ByteTrack.
2. Quando um veículo cruza a linha virtual, envia `POST /api/rounds/count-events` ao backend.
3. O backend incrementa `CurrentCount` do round atual e faz broadcast via SignalR (`count_updated`).
4. O frontend React recebe o evento e atualiza o contador na tela em tempo real.
5. Quando o timer do round expira, o `RoundWorker` (BackgroundService) encerra o round e inicia outro automaticamente via SignalR (`round_settled`).

---

## Como Rodar

São **3 processos separados**, cada um em seu terminal. Todos devem partir da raiz `videoBetTransit/`.

```bash
# Terminal 1 — Backend .NET
cd TrafficCounter.Api
dotnet run

# Terminal 2 — Frontend React
cd traffic-counter-front
npm run dev

# Terminal 3 — Engine Python (YOLO)
python app.py
```

Ou simplesmente execute `start.bat` (Windows) para abrir os 3 terminais de uma vez.

---

## Estrutura de Pastas

```
videoBetTransit/
├── app.py                  # Engine de detecção (Python)
├── backend_client.py       # Cliente HTTP para enviar eventos ao .NET
├── config.json             # Configuração da engine (stream, ROI, linha, modelo)
├── requirements.txt        # Dependências Python
├── yolov8n.pt              # Modelo YOLOv8 nano
├── yolov8m.pt              # Modelo YOLOv8 medium
├── snapshots/              # Crops salvos de veículos detectados
├── start.bat               # Script para iniciar tudo no Windows
├── test_detection.py       # Script auxiliar para testar detecção isolada
│
├── TrafficCounter.Api/     # Backend .NET 8
│   ├── Program.cs          # Bootstrap (CORS, SignalR, Controllers, RoundWorker)
│   ├── Controllers/
│   │   └── RoundsController.cs   # Endpoints REST
│   ├── Hubs/
│   │   └── RoundHub.cs           # Hub SignalR (conexão/desconexão)
│   ├── Models/
│   │   └── Round.cs              # Round, Range, CountEvent
│   ├── Services/
│   │   ├── RoundService.cs       # Lógica de rounds (in-memory)
│   │   └── RoundWorker.cs        # BackgroundService (auto-settle por timer)
│   └── Properties/
│       └── launchSettings.json   # Porta fixa: 5000
│
└── traffic-counter-front/  # Frontend React + Vite
    └── src/
        ├── App.jsx               # Componente raiz, orquestra tudo
        ├── main.jsx              # Entry point
        ├── styles.css            # Estilos globais (dark mode, glassmorphism)
        ├── components/
        │   ├── CounterCard.jsx   # Exibe contagem atual
        │   ├── TimerCard.jsx     # Exibe tempo restante (mm:ss)
        │   ├── RangeCard.jsx     # Exibe faixa de odds
        │   ├── HistoryCard.jsx   # Exibe round finalizado
        │   └── VideoPlayer.jsx   # Player HLS com hls.js
        ├── services/
        │   ├── roundApi.js       # Chamadas REST (axios)
        │   └── roundSignalr.js   # Conexão SignalR
        └── utils/
            └── time.js           # Cálculo de tempo restante
```

---

## Detalhamento dos Componentes

### 1. Engine Python (`app.py`)

| Item | Detalhe |
|---|---|
| **Modelo** | YOLOv8 (configurável via `config.json`, campo `model`) |
| **Tracker** | ByteTrack (`bytetrack.yaml`) |
| **Stream** | HLS via `cv2.VideoCapture` com reconexão automática (`StreamCapture`) |
| **Contagem** | Detecta veículos (car, motorcycle, bus, truck), filtra pela ROI, e conta quando o centro do bounding box cruza a linha virtual |
| **Direção** | `"any"` — conta veículos em qualquer sentido (configurável: `"up"`, `"down"`, `"any"`) |
| **Envio** | `BackendClient.send_count_event()` — faz `POST` em thread separada para não bloquear o loop de vídeo |
| **Snapshots** | Salva recortes dos veículos em `snapshots/` (desabilitável via `config.json`) |

**Configuração principal (`config.json`):**
- `stream_url` — URL do stream HLS
- `line` — Coordenadas (x1,y1,x2,y2) da linha virtual de cruzamento
- `roi` — Região de interesse (x, y, w, h) que filtra onde procurar veículos
- `conf` — Confiança mínima do YOLO (0.25)
- `count_direction` — `"up"`, `"down"` ou `"any"`
- `show_window` — Exibe janela OpenCV para debug (false em produção/headless)

### 2. Backend .NET (`TrafficCounter.Api/`)

**Endpoints REST (`RoundsController`):**

| Método | Rota | Descrição |
|---|---|---|
| `GET` | `/api/rounds/current` | Retorna o round ativo (status, contagem, timer, faixas) |
| `GET` | `/api/rounds/history` | Últimos 20 rounds encerrados |
| `POST` | `/api/rounds/settle` | Encerra o round manualmente e cria um novo |
| `POST` | `/api/rounds/count-events` | Recebe evento de veículo → incrementa contagem → broadcast SignalR |

**SignalR Hub (`/hubs/round`):**

| Evento | Payload | Disparo |
|---|---|---|
| `count_updated` | `Round` (objeto completo) | Cada vez que um veículo é contado |
| `round_settled` | `Round` (novo round) | Quando um round encerra (manual ou auto) |

**RoundService (in-memory):**
- Singleton registrado no DI
- `IncrementCount()` → `lock`-safe, incrementa `CurrentCount++` do round atual
- `Settle(string currentId)` → Thread-safe, encerra o round, cria novo. Retorna `null` se já foi encerrado (previne race condition)
- Cada round dura **5 minutos** (`DateTime.UtcNow.AddMinutes(5)`)
- Faixas de odds fixas: 0–10 (3.5x), 11–20 (2.2x), 21–35 (1.8x), 36+ (4.0x)

**RoundWorker (BackgroundService):**
- Loop infinito com `Task.Delay(1000)` — checa a cada segundo se `DateTime.UtcNow >= current.EndsAt`
- Quando o tempo expira, chama `Settle()` automaticamente e faz broadcast `round_settled` via SignalR

**CORS:**
- Permite origens: `localhost:5173`, `localhost:3000`, `127.0.0.1:5173`
- `AllowCredentials` habilitado (requerido pelo SignalR)

### 3. Frontend React (`traffic-counter-front/`)

| Tecnologia | Uso |
|---|---|
| React + Vite | Framework e bundler |
| Axios | Chamadas REST para o backend |
| @microsoft/signalr | Conexão WebSocket para tempo real |
| hls.js | Player de vídeo HLS |

**Fluxo do `App.jsx`:**
1. No mount, busca o round atual via REST (`getCurrentRound`)
2. Busca histórico via REST (`getRoundHistory`)
3. Abre conexão SignalR e escuta `count_updated` (atualiza state do round) e `round_settled` (recarrega dados)
4. Timer local (`setInterval` de 1s) calcula tempo restante com base em `round.endsAt`
5. Botão "Encerrar / Novo Round" chama `POST /api/rounds/settle`

**Gerenciamento de conexão SignalR (`roundSignalr.js`):**
- Trata React Strict Mode (double-mount) com guard de estado da conexão
- `withAutomaticReconnect()` habilitado
- Referência singleton (`connection`) para evitar múltiplas conexões

---

## Pontos Importantes

- **Armazenamento**: Tudo é **in-memory**. Reiniciar o backend .NET zera todas as contagens e o histórico.
- **Contagem por round**: O backend incrementa sua própria contagem (`+1` por evento). A engine Python NÃO controla o total do round — ela apenas sinaliza que um veículo cruzou a linha.
- **QuickEdit do Windows**: Clicar no terminal CMD do Python pode congelar a execução. Apertar `ESC` ou `Enter` desfaz isso.
- **Porta fixa**: O backend DEVE rodar na porta 5000 (configurado em `launchSettings.json`). O frontend e a engine Python estão hardcoded para apontar para `localhost:5000`.
