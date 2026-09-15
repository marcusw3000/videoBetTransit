import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  outputDir: '../artifacts/browser-results',
  use: { baseURL: 'http://127.0.0.1:5175', headless: true, trace: 'retain-on-failure' },
  webServer: {
    command: 'npm run dev -- --host 127.0.0.1 --port 5175 --strictPort --configLoader native',
    url: 'http://127.0.0.1:5175',
    reuseExistingServer: false,
  },
})
