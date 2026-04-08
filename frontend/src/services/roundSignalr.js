import * as signalR from '@microsoft/signalr'
import { SIGNALR_BASE_URL } from '../config'
import { normalizeRoundContract } from '../utils/roundContract'

let connection = null
let connectionPromise = null

const MAX_RETRIES = 10
const RETRY_DELAY_MS = 3000

export async function startRoundConnection({ onCountUpdated, onRoundSettled }) {
  // Se já existe uma conexão ativa, retorna ela.
  if (connection && connection.state === signalR.HubConnectionState.Connected) {
    return connection
  }

  // Se já existe uma tentativa de conexão em andamento, espera ela.
  if (connectionPromise) {
    return connectionPromise
  }

  // Limpa conexão anterior morta, por exemplo após cleanup do Strict Mode.
  if (connection) {
    connection.off('count_updated')
    connection.off('round_settled')
    connection = null
  }

  const conn = new signalR.HubConnectionBuilder()
    .withUrl(`${SIGNALR_BASE_URL}/hubs/round`)
    .withAutomaticReconnect()
    .build()

  conn.on('count_updated', (data) => {
    onCountUpdated?.(normalizeRoundContract(data))
  })

  conn.on('round_settled', (data) => {
    onRoundSettled?.(normalizeRoundContract(data))
  })

  connectionPromise = connectWithRetry(conn, 0)

  return connectionPromise
}

async function connectWithRetry(conn, attempt) {
  try {
    await conn.start()
    connection = conn
    connectionPromise = null
    console.log('[SignalR] Conectado com sucesso!')
    return conn
  } catch (err) {
    if (attempt < MAX_RETRIES) {
      console.warn(`[SignalR] Tentativa ${attempt + 1}/${MAX_RETRIES} falhou. Retentando em ${RETRY_DELAY_MS / 1000}s...`)
      await new Promise((resolve) => setTimeout(resolve, RETRY_DELAY_MS))
      return connectWithRetry(conn, attempt + 1)
    }
    connectionPromise = null
    connection = null
    throw err
  }
}

export async function stopRoundConnection() {
  connectionPromise = null

  if (connection) {
    const conn = connection
    connection = null
    await conn.stop()
  }
}
