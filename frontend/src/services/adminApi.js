import { api } from './apiClient'

export function voidRound(roundId, reason, reasonCode = 'manual_intervention') {
  return api.post(`/admin/rounds/${roundId}/void`, { reason, reasonCode })
}

export const getRoundConfiguration = (id) => api.get(`/admin/rounds/${id}/configuration`).then(r => r.data)
export const getAudit = (target, page = 1) => api.get("/admin/audit", { params: { target, page } }).then(r => r.data)
