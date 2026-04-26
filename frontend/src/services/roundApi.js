import axios from 'axios'
import { API_BASE_URL } from '../config'
import { normalizeRoundContract } from '../utils/roundContract'

const api = axios.create({
  baseURL: API_BASE_URL,
})

const MAX_RETRIES = 10
const RETRY_DELAY_MS = 3000

async function withRetry(fn, attempt = 0) {
  try {
    return await fn()
  } catch (err) {
    if (attempt < MAX_RETRIES && (err.code === 'ERR_NETWORK' || err.code === 'ECONNREFUSED')) {
      console.warn(`[API] Tentativa ${attempt + 1}/${MAX_RETRIES} falhou. Retentando em ${RETRY_DELAY_MS / 1000}s...`)
      await new Promise(resolve => setTimeout(resolve, RETRY_DELAY_MS))
      return withRetry(fn, attempt + 1)
    }
    throw err
  }
}

function normalizeCrossingEvent(event) {
  if (!event) return null

  return {
    id: event.id || event.eventHash || '',
    roundId: event.roundId || '',
    cameraId: event.cameraId || '',
    trackId: String(event.trackId ?? ''),
    vehicleType: event.objectClass || event.vehicleType || 'unknown',
    objectClass: event.objectClass || event.vehicleType || 'unknown',
    direction: event.direction || 'unknown',
    lineId: event.lineId || '',
    confidence: Number(event.confidence ?? 0),
    frameNumber: Number(event.frameNumber ?? 0),
    snapshotUrl: event.snapshotUrl || null,
    source: event.source || null,
    streamProfileId: event.streamProfileId || null,
    countBefore: event.countBefore ?? null,
    countAfter: event.countAfter ?? null,
    previousEventHash: event.previousEventHash || null,
    eventHash: event.eventHash || '',
    timestampUtc: event.timestampUtc || null,
    counted: true,
  }
}

function normalizeTimelineItem(item) {
  if (!item) return null

  return {
    kind: item.kind || 'round_event',
    roundId: item.roundId || '',
    timestampUtc: item.timestampUtc || null,
    eventType: item.eventType || '',
    roundStatus: item.roundStatus || '',
    countValue: item.countValue ?? null,
    reason: item.reason || null,
    source: item.source || null,
    cameraId: item.cameraId || null,
    trackId: item.trackId ?? null,
    objectClass: item.objectClass || null,
    direction: item.direction || null,
    lineId: item.lineId || null,
    snapshotUrl: item.snapshotUrl || null,
    confidence: item.confidence ?? null,
    streamProfileId: item.streamProfileId || null,
    countBefore: item.countBefore ?? null,
    countAfter: item.countAfter ?? null,
    eventHash: item.eventHash || null,
  }
}

export async function getRoundById(roundId) {
  const { data } = await withRetry(() => api.get(`/rounds/${roundId}`))
  return normalizeRoundContract(data)
}

export async function getCurrentRound(cameraId) {
  const params = cameraId ? { cameraId } : undefined
  const { data } = await withRetry(() => api.get('/rounds/current', { params }))
  return normalizeRoundContract(data)
}

export async function getRecentRounds(cameraId, limit = 12) {
  const params = { limit }
  if (cameraId) params.cameraId = cameraId

  const { data } = await withRetry(() => api.get('/rounds/recent', { params }))
  return Array.isArray(data) ? data.map(normalizeRoundContract).filter(Boolean) : []
}

export async function getRoundHistory(cameraId, cameraIds = []) {
  const normalizedCameraId = String(cameraId || '').trim()
  const normalizedCameraIds = Array.isArray(cameraIds)
    ? cameraIds.map((item) => String(item || '').trim()).filter(Boolean)
    : []

  const params = {}
  if (normalizedCameraId) {
    params.cameraId = normalizedCameraId
  } else if (normalizedCameraIds.length > 0) {
    params.cameraIds = normalizedCameraIds.join(',')
  }

  const { data } = await withRetry(() => api.get('/rounds/history', { params }))
  return Array.isArray(data) ? data.map(normalizeRoundContract).filter(Boolean) : []
}

export async function getRoundCountEvents(roundId) {
  const { data } = await withRetry(() => api.get(`/rounds/${roundId}/count-events`))
  return Array.isArray(data) ? data.map(normalizeCrossingEvent).filter(Boolean) : []
}

export async function getRoundTimeline(roundId) {
  const { data } = await withRetry(() => api.get(`/rounds/${roundId}/timeline`))
  return Array.isArray(data) ? data.map(normalizeTimelineItem).filter(Boolean) : []
}
