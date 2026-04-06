import axios from 'axios'
import { API_BASE_URL } from '../config'

const api = axios.create({ baseURL: API_BASE_URL })

const apiKey = import.meta.env.VITE_API_KEY || 'CHANGE_ME'

api.interceptors.request.use((cfg) => {
  cfg.headers['X-API-Key'] = apiKey
  return cfg
})

export function voidRound(roundId, reason = 'Anulado manualmente pelo painel admin') {
  return api.post(`/internal/rounds/${roundId}/void`, { reason })
}
