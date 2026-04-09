import axios from 'axios'
import { API_BASE_URL } from '../config'

const api = axios.create({
  baseURL: API_BASE_URL,
})

function normalizeBet(bet) {
  if (!bet) return null

  return {
    id: bet.id || '',
    providerBetId: bet.providerBetId || '',
    transactionId: bet.transactionId || '',
    gameSessionId: bet.gameSessionId || '',
    roundId: bet.roundId || '',
    cameraId: bet.cameraId || '',
    roundMode: (bet.roundMode || 'normal').toLowerCase(),
    marketId: bet.marketId || '',
    marketType: bet.marketType || '',
    marketLabel: bet.marketLabel || '',
    odds: Number(bet.odds ?? 0),
    threshold: bet.threshold ?? null,
    min: bet.min ?? null,
    max: bet.max ?? null,
    targetValue: bet.targetValue ?? null,
    stakeAmount: Number(bet.stakeAmount ?? 0),
    potentialPayout: Number(bet.potentialPayout ?? 0),
    currency: bet.currency || 'BRL',
    status: (bet.status || '').toLowerCase(),
    placedAt: bet.placedAt || null,
    acceptedAt: bet.acceptedAt || null,
    settledAt: bet.settledAt || null,
    voidedAt: bet.voidedAt || null,
    rollbackOfTransactionId: bet.rollbackOfTransactionId || null,
    playerRef: bet.playerRef || null,
    operatorRef: bet.operatorRef || null,
    metadataJson: bet.metadataJson || null,
  }
}

export async function placeBet(payload) {
  const { data } = await api.post('/bets', payload)
  return normalizeBet(data)
}
