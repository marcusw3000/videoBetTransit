export function pendingBetKey(username) { return `videobet.pending.${username}` }
export function readPendingBet(storage, username) {
  try { return JSON.parse(storage.getItem(pendingBetKey(username)) || 'null') }
  catch { return null }
}
export function savePendingBet(storage, username, payload) {
  // Fail before sending if the browser cannot preserve the idempotency key.
  storage.setItem(pendingBetKey(username), JSON.stringify(payload))
}
export function clearPendingBet(storage, username) { storage.removeItem(pendingBetKey(username)) }
export function isDefinitiveRejection(error) {
  const status = error?.response?.status
  return status >= 400 && status < 500 && ![401, 408, 429].includes(status)
}
