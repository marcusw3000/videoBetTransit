import axios from 'axios'
import { API_BASE_URL, BACKEND_API_KEY } from '../config'

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: BACKEND_API_KEY ? { 'X-API-Key': BACKEND_API_KEY } : {},
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

export async function getCurrentRound() {
  const { data } = await withRetry(() => api.get('/rounds/current'))
  return data
}

export async function getRoundHistory() {
  const { data } = await withRetry(() => api.get('/rounds/history'))
  return data
}

export async function getRoundCountEvents(roundId) {
  const { data } = await withRetry(() => api.get(`/rounds/${roundId}/count-events`))
  return data
}

export async function settleRound() {
  const { data } = await api.post('/rounds/settle', {})
  return data
}
