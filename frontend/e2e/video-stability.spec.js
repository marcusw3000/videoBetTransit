import { test, expect } from '@playwright/test'

async function harness(page, component) {
  await page.route('**/src/main.jsx*', route => route.fulfill({ contentType: 'text/javascript', body: `
    import {React, mount, VideoPlayer, CameraManagementCard} from '/e2e/fixtures/media-harness.jsx';
    function Harness() { ${component} }
    mount(Harness);
  ` }))
}

test('parent ticks and playable transition do not recreate the HLS decoder', async ({ page }) => {
  await page.addInitScript(() => {
    const canPlayType = HTMLMediaElement.prototype.canPlayType
    HTMLMediaElement.prototype.canPlayType = function (type) {
      // A native "maybe" must not skip the available HLS.js decoder.
      return type.includes('mpegurl') ? 'maybe' : canPlayType.call(this, type)
    }
  })
  await page.route('**/node_modules/.vite/deps/hls__js.js*', route => route.fulfill({ contentType: 'text/javascript', body: `
    export default class Hls {
      static isSupported() { return true }
      static Events = {MANIFEST_PARSED: 'parsed', ERROR: 'error'};
      static ErrorTypes = {};
      constructor() { window.decoderStarts = (window.decoderStarts || 0) + 1 }
      loadSource() {} attachMedia() {}
      on(event, callback) { if (event === 'parsed') setTimeout(callback, 10) }
      destroy() { window.decoderStops = (window.decoderStops || 0) + 1 }
    }
  ` }))
  await harness(page, `
    const [tick, setTick] = React.useState(0);
    const [source, setSource] = React.useState('/test-camera.m3u8');
    React.useEffect(() => { const t = setInterval(() => setTick(n => n+1), 100); return () => clearInterval(t) }, []);
    return React.createElement(React.Fragment, null,
      React.createElement('button', {onClick: () => setSource('/next-camera.m3u8')}, 'Switch camera'),
      React.createElement(VideoPlayer, {src: source, title: 'Camera ' + tick, onFirstPlayableFrame: () => {}, onStreamStatusChange: () => {}}));
  `)
  await page.goto('/')
  await expect.poll(() => page.evaluate(() => window.decoderStarts)).toBe(1)
  await page.waitForTimeout(1600)
  expect(await page.evaluate(() => window.decoderStarts)).toBe(1)
  await page.getByRole('button', { name: 'Switch camera' }).click()
  await expect.poll(() => page.evaluate(() => window.decoderStarts)).toBeGreaterThan(1)
  const afterSwitch = await page.evaluate(() => window.decoderStarts)
  await page.waitForTimeout(1600)
  expect(await page.evaluate(() => window.decoderStarts)).toBe(afterSwitch)
})

test('management polling preserves local edits and the revision they were based on', async ({ page }) => {
  let revision = 1
  let sentDraft
  await page.route('**/admin/camera-management**', async route => {
    if (route.request().method() === 'OPTIONS') return route.fulfill({ status: 204,
      headers: {'Access-Control-Allow-Origin': 'http://127.0.0.1:5175', 'Access-Control-Allow-Credentials': 'true',
        'Access-Control-Allow-Methods': 'GET,PUT,OPTIONS', 'Access-Control-Allow-Headers': 'Content-Type,X-CSRF-Token,X-Requested-With'} })
    if (route.request().method() === 'PUT') sentDraft = route.request().postDataJSON()
    return route.fulfill({ json: {isActive: true, revision, draftApplied: false,
      draftConfigurationJson: JSON.stringify({roi: {x: 10,y: 10,w: 100,h: 100}, line: {x1: 0,y1: 50,x2: 100,y2: 50}})},
      headers: {'Access-Control-Allow-Origin': 'http://127.0.0.1:5175', 'Access-Control-Allow-Credentials': 'true'} })
  })
  await page.route('**/auth/csrf', route => route.fulfill({json:{token:'test'}, headers: {
    'Access-Control-Allow-Origin': 'http://127.0.0.1:5175', 'Access-Control-Allow-Credentials': 'true'} }))
  await harness(page, `return React.createElement(CameraManagementCard, {cameraId:'camera-a', streamProfileId:'profile-a'});`)
  await page.goto('/')
  const field = page.getByRole('group', {name:'ROI'}).getByRole('spinbutton').first()
  await expect(field).toHaveValue('10')
  await field.fill('123')
  revision = 2
  await page.waitForTimeout(3400)
  await expect(field).toHaveValue('123')
  await page.getByRole('button', {name:'Atualizar preview de teste'}).click()
  await expect.poll(() => sentDraft?.roi?.x).toBe(123)
  expect(sentDraft.expectedRevision).toBe(1)
})
