import { api } from './apiClient'

export const listSessions = (activeOnly = false) => api.get('/streams', { params: { activeOnly } })
export const createSession = (payload) => api.post('/streams', payload)
export const startSession = (id) => api.post(`/streams/${id}/start`)
export const stopSession = (id) => api.post(`/streams/${id}/stop`)
export const getSession = (id) => api.get(`/streams/${id}`)
export const getMetrics = (id) => api.get(`/streams/${id}/metrics`)
export const getEvents = (id, pageSize = 20) =>
  api.get(`/streams/${id}/events`, { params: { page: 1, pageSize } })
