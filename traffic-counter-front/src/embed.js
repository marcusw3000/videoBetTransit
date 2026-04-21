const EMBED_CONFIG_EVENT = 'videobettransit:config-update'
const EMBED_EVENT_PREFIX = 'videobettransit:'

const THEME_PRESETS = {
  midnight: {
    accent: '#8b8bc8',
    highlight: '#f0b31f',
    live: '#30d16b',
    buttonFrom: '#ffffff',
    buttonTo: '#d4d4e8',
    buttonText: '#111111',
  },
  emerald: {
    accent: '#7ccf9a',
    highlight: '#ffd166',
    live: '#22c55e',
    buttonFrom: '#f3fff8',
    buttonTo: '#b7f0cd',
    buttonText: '#0f1720',
  },
  sunset: {
    accent: '#ff9b71',
    highlight: '#ffd166',
    live: '#34d399',
    buttonFrom: '#fff4ed',
    buttonTo: '#ffd0b8',
    buttonText: '#22110d',
  },
}

function getWindowRef() {
  if (typeof window === 'undefined') return null
  return window
}

function getSearchParams() {
  const win = getWindowRef()
  if (!win) return new URLSearchParams()
  return new URLSearchParams(win.location.search)
}

function getGlobalConfig() {
  const win = getWindowRef()
  if (!win) return {}
  return win.VideoBetTransitEmbedConfig || {}
}

function readValue(key, fallback = '') {
  const params = getSearchParams()
  const globalConfig = getGlobalConfig()

  if (params.has(key)) return params.get(key) || fallback
  if (globalConfig[key] != null && globalConfig[key] !== '') return globalConfig[key]
  return fallback
}

function parseStakeOptions(rawValue) {
  const values = Array.isArray(rawValue)
    ? rawValue
    : typeof rawValue === 'string'
      ? rawValue.split(',')
      : []

  const parsed = values
    .map((value) => Number.parseFloat(String(value).replace(',', '.')))
    .filter((value) => Number.isFinite(value) && value > 0)

  return parsed.length > 0 ? parsed : [5, 10, 20, 50]
}

function hexToRgbTriplet(color, fallback) {
  const hex = (color || '').replace('#', '').trim()
  if (![3, 6].includes(hex.length)) return fallback

  const normalized = hex.length === 3
    ? hex.split('').map((part) => `${part}${part}`).join('')
    : hex

  const value = Number.parseInt(normalized, 16)
  if (Number.isNaN(value)) return fallback

  return `${(value >> 16) & 255}, ${(value >> 8) & 255}, ${value & 255}`
}

function getThemeConfig(theme) {
  if (theme && typeof theme === 'object') {
    return {
      ...THEME_PRESETS.midnight,
      ...theme,
    }
  }

  const themeKey = typeof theme === 'string' && theme.trim()
    ? theme.trim().toLowerCase()
    : 'midnight'

  return THEME_PRESETS[themeKey] || THEME_PRESETS.midnight
}

export function getEmbedConfig() {
  const globalConfig = getGlobalConfig()
  const theme = globalConfig.theme ?? readValue('theme', import.meta.env.VITE_THEME || 'midnight')
  const stakeOptions = parseStakeOptions(
    globalConfig.stakeOptions ?? readValue('stakeOptions', import.meta.env.VITE_STAKE_OPTIONS || '5,10,20,50'),
  )
  const defaultStake = Number.parseFloat(String(
    globalConfig.defaultStake ?? readValue('defaultStake', import.meta.env.VITE_DEFAULT_STAKE || stakeOptions[0]),
  ).replace(',', '.'))

  return {
    brand: readValue('brand', import.meta.env.VITE_BRAND || 'Rodovia Market'),
    locale: readValue('locale', import.meta.env.VITE_LOCALE || 'pt-BR'),
    cameraId: readValue('cameraId', import.meta.env.VITE_CAMERA_ID || 'cam_001'),
    cameraLabel: readValue('cameraLabel', import.meta.env.VITE_CAMERA_LABEL || 'Rodovia Norte - Faixa A'),
    currency: readValue('currency', import.meta.env.VITE_CURRENCY || 'BRL'),
    timezone: readValue('timezone', import.meta.env.VITE_TIMEZONE || 'America/Sao_Paulo'),
    stakeOptions,
    defaultStake: Number.isFinite(defaultStake) && defaultStake > 0 ? defaultStake : stakeOptions[0],
    theme,
    mode: readValue('mode', import.meta.env.VITE_APP_MODE || 'player').toLowerCase(),
    callbacks: globalConfig.callbacks || {},
  }
}

export function applyEmbedTheme(config) {
  const win = getWindowRef()
  if (!win?.document?.documentElement) return

  const theme = getThemeConfig(config?.theme)
  const rootStyle = win.document.documentElement.style

  rootStyle.setProperty('--brand-accent', theme.accent)
  rootStyle.setProperty('--brand-accent-rgb', hexToRgbTriplet(theme.accent, '139, 139, 200'))
  rootStyle.setProperty('--brand-highlight', theme.highlight)
  rootStyle.setProperty('--brand-highlight-rgb', hexToRgbTriplet(theme.highlight, '240, 179, 31'))
  rootStyle.setProperty('--brand-live', theme.live)
  rootStyle.setProperty('--brand-live-rgb', hexToRgbTriplet(theme.live, '48, 209, 107'))
  rootStyle.setProperty('--brand-button-from', theme.buttonFrom)
  rootStyle.setProperty('--brand-button-to', theme.buttonTo)
  rootStyle.setProperty('--brand-button-text', theme.buttonText)
}

function toCallbackName(eventName) {
  return `on${eventName
    .split('-')
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join('')}`
}

export function emitEmbedEvent(eventName, payload, config = getEmbedConfig()) {
  const win = getWindowRef()
  if (!win) return

  const eventCameraId = payload?.cameraId || config.cameraId

  const detail = {
    source: 'videobettransit',
    event: eventName,
    payload,
    config: {
      brand: config.brand,
      locale: config.locale,
      cameraId: eventCameraId,
      currency: config.currency,
      timezone: config.timezone,
      mode: config.mode,
    },
    emittedAt: new Date().toISOString(),
  }

  win.dispatchEvent(new CustomEvent(`${EMBED_EVENT_PREFIX}${eventName}`, { detail }))

  if (win.parent && win.parent !== win) {
    win.parent.postMessage(detail, '*')
  }

  const callbackName = toCallbackName(eventName)
  config.callbacks?.[callbackName]?.(payload, detail)
  win.VideoBetTransitHost?.[callbackName]?.(payload, detail)
}

export function installEmbedSdk() {
  const win = getWindowRef()
  if (!win) return

  win.VideoBetTransitWidget = {
    getConfig() {
      return getEmbedConfig()
    },
    setConfig(nextConfig = {}) {
      const previous = win.VideoBetTransitEmbedConfig || {}
      win.VideoBetTransitEmbedConfig = {
        ...previous,
        ...nextConfig,
      }
      win.dispatchEvent(new CustomEvent(EMBED_CONFIG_EVENT, { detail: getEmbedConfig() }))
    },
    on(eventName, handler) {
      const listener = (event) => handler(event.detail?.payload, event.detail)
      win.addEventListener(`${EMBED_EVENT_PREFIX}${eventName}`, listener)
      return () => win.removeEventListener(`${EMBED_EVENT_PREFIX}${eventName}`, listener)
    },
  }
}

export { EMBED_CONFIG_EVENT }
