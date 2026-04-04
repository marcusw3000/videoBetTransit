import * as signalR from '@microsoft/signalr'
import { SIGNALR_BASE_URL } from '../config'

let connection = null

export async function startMetricsConnection({ sessionId, onMetricsUpdated, onStatusChanged }) {
  if (connection) {
    await stopMetricsConnection()
  }

  connection = new signalR.HubConnectionBuilder()
    .withUrl(`${SIGNALR_BASE_URL}/hubs/metrics`)
    .withAutomaticReconnect()
    .configureLogging(signalR.LogLevel.Warning)
    .build()

  connection.on('metrics_updated', onMetricsUpdated)
  connection.on('session_status_changed', onStatusChanged)

  await connection.start()
  await connection.invoke('JoinSession', sessionId)
}

export async function stopMetricsConnection() {
  if (!connection) return
  try {
    await connection.stop()
  } catch {
    // ignore
  }
  connection = null
}
