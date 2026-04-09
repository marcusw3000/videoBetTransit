function normalizeMarket(market) {
  if (!market) return null

  return {
    id: market.marketId || market.id || '',
    marketId: market.marketId || market.id || '',
    marketType: market.marketType || '',
    label: market.label || '',
    min: market.min ?? 0,
    max: market.max ?? 0,
    targetValue: market.targetValue ?? null,
    odds: Number(market.odds ?? 0),
    isWinner: market.isWinner ?? null,
  }
}

export function normalizeRoundContract(round) {
  if (!round) return null

  const status = (round.status || '').toLowerCase()
  const marketsSource = round.markets || round.ranges || []
  const markets = marketsSource
    .map(normalizeMarket)
    .filter(Boolean)

  return {
    id: round.roundId || round.id || '',
    roundId: round.roundId || round.id || '',
    cameraId: round.cameraId || (Array.isArray(round.cameraIds) ? round.cameraIds[0] || '' : ''),
    displayName: round.displayName || 'Rodada Turbo',
    status,
    createdAt: round.createdAt || null,
    betCloseAt: round.betCloseAt || null,
    endsAt: round.endsAt || null,
    settledAt: round.settledAt || null,
    voidedAt: round.voidedAt || null,
    voidReason: round.voidReason || null,
    currentCount: round.currentCount ?? 0,
    finalCount: round.finalCount ?? null,
    isSuspended: round.isSuspended ?? status !== 'open',
    cameraIds: Array.isArray(round.cameraIds) ? round.cameraIds : [],
    eventsCount: round.eventsCount ?? 0,
    markets,
  }
}
