import test from 'node:test'
import assert from 'node:assert/strict'
import { readPendingBet, savePendingBet, clearPendingBet, isDefinitiveRejection } from '../src/utils/pendingBet.js'

test('a refresh preserves payload and separates player identities', () => {
  const values = new Map()
  const storage = { getItem: k => values.get(k), setItem: (k, v) => values.set(k, v), removeItem: k => values.delete(k) }
  const payload = { transactionId: 'stable', roundId: 'old-round', stakeAmount: 10 }
  savePendingBet(storage, 'alice', payload)
  assert.deepEqual(readPendingBet(storage, 'alice'), payload)
  assert.equal(readPendingBet(storage, 'bob'), null)
  clearPendingBet(storage, 'alice')
  assert.equal(readPendingBet(storage, 'alice'), null)
})

test('unknown outcomes retain the attempt; definitive rejections release it', () => {
  for (const status of [undefined, 401, 408, 429, 500, 503])
    assert.equal(isDefinitiveRejection({ response: { status } }), false)
  for (const status of [400, 403, 404, 409, 422])
    assert.equal(isDefinitiveRejection({ response: { status } }), true)
})

test('storage failure aborts before an unsafe new request can be sent', () => {
  assert.throws(() => savePendingBet({ setItem() { throw new Error('blocked') } }, 'player', {}))
})
