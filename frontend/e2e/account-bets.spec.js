import { test, expect } from '@playwright/test'

async function mockApi(page, { loggedIn = true, pending = false, admin = false } = {}) {
  let authenticated = loggedIn
  let failNextBet = pending
  const requests = []
  const now = Date.now()
  const round = { roundId: 'round-1', cameraId: 'cam_001', status: 'open', currentCount: 3,
    createdAt: new Date(now - 1000).toISOString(), betCloseAt: new Date(now + 60000).toISOString(),
    endsAt: new Date(now + 120000).toISOString(), markets: [
      { marketId: 'market-1', marketType: 'under', label: 'Menos de 20', odds: 2, targetValue: 20 },
    ] }
  await page.route('http://127.0.0.1:8090/**', route => route.fulfill({ status: 200, contentType: 'application/json', body: '{}' }))
  const bets = [{ id: 'bet-old', marketLabel: 'Resultado anterior', currency: 'BRL', stakeAmount: 5,
    status: 'settled_loss', placedAt: new Date(now - 100000).toISOString() }]
  await page.route('http://127.0.0.1:8080/**', async route => {
    const request = route.request()
    const url = new URL(request.url())
    const headers = { 'Access-Control-Allow-Origin': 'http://127.0.0.1:5175',
      'Access-Control-Allow-Credentials': 'true', 'Access-Control-Allow-Headers': 'Content-Type,X-CSRF-Token,X-Requested-With',
      'Access-Control-Allow-Methods': 'GET,POST,OPTIONS' }
    const respond = (status, body) => route.fulfill({ status, headers, contentType: 'application/json', body: JSON.stringify(body) })
    if (request.method() === 'OPTIONS') return respond(200, {})
    if (url.pathname === '/auth/csrf') return respond(200, { token: 'csrf-test' })
    if (url.pathname === '/auth/me') return respond(authenticated ? 200 : 401, authenticated ? { username: admin ? 'admin' : 'player', role: admin ? 'admin' : 'player', mode: 'demo' } : {})
    if (url.pathname === '/auth/login') { authenticated = true; return respond(200, { username: admin ? 'admin' : 'player', role: admin ? 'admin' : 'player', mode: 'demo' }) }
    if (url.pathname === '/auth/logout') { authenticated = false; return respond(200, {}) }
    if (url.pathname === '/rounds/current') return respond(200, round)
    if (url.pathname === '/rounds/history') return respond(200, [])
    if (url.pathname === '/streams') return respond(200, [])
    if (url.pathname === '/rounds/recent') return respond(200, [round])
    if (url.pathname === '/rounds/round-1') return respond(200, round)
    if (url.pathname.endsWith('/count-events') || url.pathname.endsWith('/timeline')) return respond(200, [])
    if (url.pathname === '/admin/audit') return respond(200, [{ id: 'audit1', actor: 'admin', action: 'round.void',
      target: 'historical-round', outcome: 'completed', reasonCode: 'stream_loss', reason: 'Interrupção confirmada', timestampUtc: new Date(now).toISOString() }])
    if (url.pathname.endsWith('/configuration')) return respond(200, { available: true, configurationVersion: 'test-version-1', operational: { cameraId: 'camera1', countDirection: 'down' }, rules: { version: 'normal-v1' } })
    if (url.pathname.startsWith('/admin/rounds/') && url.pathname.endsWith('/void')) {
      requests.push(request.postDataJSON()); round.status = 'void'; return respond(200, { voided: true })
    }

    if (url.pathname === '/bets' && request.method() === 'POST') {
      const payload = request.postDataJSON()
      requests.push(payload)
      const bet = { ...payload, id: 'bet-new', marketLabel: 'Menos de 20', status: 'accepted', placedAt: new Date().toISOString() }
      if (!bets.some(item => item.id === bet.id)) bets.unshift(bet)
      if (failNextBet) { failNextBet = false; return respond(503, { error: 'temporary' }) }
      return respond(200, bet)
    }
    if (url.pathname === '/bets') {
      const status = url.searchParams.get('status')
      const items = bets.filter(b => status === 'open' ? b.status === 'accepted' : status === 'closed' ? b.status !== 'accepted' : true)
      return respond(200, { items, total: items.length })
    }
    return respond(200, {})
  })
  return requests
}

test('login, private admin view and logout', async ({ page }) => {
  await mockApi(page, { loggedIn: false })
  await page.goto('/admin')
  await page.getByLabel('Usuario', { exact: true }).fill('player')
  await page.getByLabel('Senha', { exact: true }).fill('test-password')
  await page.getByRole('button', { name: 'Entrar', exact: true }).click()
  await expect(page.getByText('Acesso restrito a administradores.')).toBeVisible()
  await page.getByRole('button', { name: 'Sair', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Entrar', exact: true })).toBeVisible()
})

test('a lost confirmation survives reload and retries the same request', async ({ page }) => {
  const requests = await mockApi(page, { pending: true })
  await page.goto('/')
  await page.locator('.betting-panel').getByRole('button', { name: 'Menos de 20 (2,00x)', exact: true }).click()
  await page.getByRole('button', { name: 'Comprar Menos de 20', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Confirmar tentativa', exact: true })).toBeVisible()
  await page.reload()
  await page.getByRole('button', { name: 'Confirmar tentativa', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Confirmar tentativa', exact: true })).toHaveCount(0)
  expect(requests).toHaveLength(2)
  expect(requests[1]).toEqual(requests[0])
  await page.getByRole('button', { name: 'Em aberto', exact: true }).click()
  await expect(page.getByRole('region', { name: 'Minhas apostas' }).getByText('Menos de 20', { exact: true })).toBeVisible()
  await expect(page.getByText('Resultado anterior', { exact: true })).toHaveCount(0)
  await page.getByRole('button', { name: 'Encerradas', exact: true }).click()
  await expect(page.getByText('Resultado anterior', { exact: true })).toBeVisible()
  await page.screenshot({ path: '../artifacts/browser-desktop.png', fullPage: true })
  await page.setViewportSize({ width: 390, height: 844 })
  await page.screenshot({ path: '../artifacts/browser-mobile.png', fullPage: true })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
})

test('admin reviews frozen configuration and supplies a structured void reason', async ({ page }) => {
  const requests = await mockApi(page, { admin: true })
  await page.goto('/admin')
  await expect(page.getByRole('heading', { name: 'Auditoria administrativa' })).toBeVisible()
  await expect(page.getByText('Versão: test-version-1')).toBeVisible()
  const cancel = page.getByRole('button', { name: 'Anular Round Selecionado' })
  await expect(cancel).toBeDisabled()
  await page.getByLabel('Motivo da anulação').selectOption('stream_loss')
  await page.getByLabel('Justificativa').fill('Transmissão interrompida')
  await expect(cancel).toBeEnabled()
  await page.screenshot({ path: '../artifacts/p01-p03-admin-desktop.png', fullPage: true })
  await page.setViewportSize({ width: 390, height: 844 })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await page.screenshot({ path: '../artifacts/p01-p03-admin-mobile.png', fullPage: true })
  await page.locator('.admin-audit-card').screenshot({ path: '../artifacts/p01-p03-audit-detail.png' })
  await cancel.click()
  await expect.poll(() => requests.length).toBe(1)
  expect(requests[0]).toEqual({ reason: 'Transmissão interrompida', reasonCode: 'stream_loss' })
})
