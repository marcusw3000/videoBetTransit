function normalizeIsoUtc(value) {
  if (typeof value !== 'string') return value

  const trimmed = value.trim()
  if (!trimmed) return trimmed

  const hasTimezone = /(?:Z|[+-]\d{2}:\d{2})$/.test(trimmed)
  return hasTimezone ? trimmed : `${trimmed}Z`
}

export function parseTimestampMs(value) {
  if (!value) return Number.NaN

  if (typeof value === 'number') {
    return Number.isFinite(value) ? value : Number.NaN
  }

  return new Date(normalizeIsoUtc(value)).getTime()
}

export function getTimeLeftInSeconds(endsAt) {
  if (!endsAt) return 0

  const end = parseTimestampMs(endsAt)
  const now = Date.now()
  const diff = Math.floor((end - now) / 1000)

  return diff > 0 ? diff : 0
}

export function getRoundPhase(round) {
  if (!round) return 'loading'

  const status = (round.status || '').toLowerCase()
  if (status === 'settled' || status === 'void') return status

  const now = Date.now()
  const end = round.endsAt ? parseTimestampMs(round.endsAt) : 0
  const close = round.betCloseAt ? parseTimestampMs(round.betCloseAt) : 0

  if (end && now >= end) return 'settling'
  if (close && now >= close) return 'closing'
  return status || 'open'
}

export function formatTime(seconds) {
  const mm = String(Math.floor(seconds / 60)).padStart(2, '0')
  const ss = String(seconds % 60).padStart(2, '0')
  return `${mm}:${ss}`
}
