export function getTimeLeftInSeconds(endsAt) {
  if (!endsAt) return 0

  const end = new Date(endsAt).getTime()
  const now = Date.now()
  const diff = Math.floor((end - now) / 1000)

  return diff > 0 ? diff : 0
}

export function getRoundPhase(round) {
  if (!round) return 'loading'

  const status = (round.status || '').toLowerCase()
  if (status === 'settled' || status === 'void') return status

  const now = Date.now()
  const end = round.endsAt ? new Date(round.endsAt).getTime() : 0
  const close = round.betCloseAt ? new Date(round.betCloseAt).getTime() : 0

  if (end && now >= end) return 'settling'
  if (close && now >= close) return 'closing'
  return status || 'open'
}

export function formatTime(seconds) {
  const mm = String(Math.floor(seconds / 60)).padStart(2, '0')
  const ss = String(seconds % 60).padStart(2, '0')
  return `${mm}:${ss}`
}
