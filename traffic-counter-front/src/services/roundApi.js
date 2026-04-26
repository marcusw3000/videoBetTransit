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

export async function getCurrentRound(cameraId) {
  const params = cameraId ? { cameraId } : undefined
  const { data } = await withRetry(() => api.get('/rounds/current', { params }))
  return normalizeRoundContract(data)
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
  return data
}
