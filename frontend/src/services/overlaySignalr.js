import * as signalR from '@microsoft/signalr'
import { SIGNALR_BASE_URL } from '../config'

let connection = null
let connectionPromise = null

const MAX_RETRIES = 10
const RETRY_DELAY_MS = 3000

export async function startOverlayConnection({ onLiveDetections }) {
  if (connection && connection.state === signalR.HubConnectionState.Connected) {
    return connection
  }

  if (connectionPromise) {
    return connectionPromise
  }

  if (connection) {
    connection.off('live_detections_updated')
    connection = null
  }

  const conn = new signalR.HubConnectionBuilder()
    .withUrl(`${SIGNALR_BASE_URL}/hubs/overlay`)
    .withAutomaticReconnect()
    .build()

  conn.on('live_detections_updated', (data) => {
    onLiveDetections?.(data)
  })

  connectionPromise = connectWithRetry(conn, 0)
  return connectionPromise
}

async function connectWithRetry(conn, attempt) {
  try {
    await conn.start()
    connection = conn
    connectionPromise = null
    console.log('[OverlaySignalR] Conectado!')
    return conn
  } catch (err) {
    if (attempt < MAX_RETRIES) {
      console.warn(`[OverlaySignalR] Tentativa ${attempt + 1}/${MAX_RETRIES} falhou. Retentando em ${RETRY_DELAY_MS / 1000}s...`)
      await new Promise(resolve => setTimeout(resolve, RETRY_DELAY_MS))
      return connectWithRetry(conn, attempt + 1)
    }
    connectionPromise = null
    connection = null
    throw err
  }
}

export async function stopOverlayConnection() {
  connectionPromise = null
  if (connection) {
    const conn = connection
    connection = null
    await conn.stop()
  }
}
