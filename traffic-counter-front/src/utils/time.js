export function getTimeLeftInSeconds(endsAt) {
  if (!endsAt) return 0

  const end = new Date(endsAt).getTime()
  const now = Date.now()
  const diff = Math.floor((end - now) / 1000)

  return diff > 0 ? diff : 0
}

export function formatTime(seconds) {
  const mm = String(Math.floor(seconds / 60)).padStart(2, '0')
  const ss = String(seconds % 60).padStart(2, '0')
  return `${mm}:${ss}`
}
