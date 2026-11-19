import { describe, expect, it } from 'vitest'
import config from '../capacitor.config.json'

// The Android app's WebView origin is https://<hostname>. The production API refuses
// any CORS origin containing "localhost", so it must be a real, https origin (T-147).
describe('capacitor config', () => {
  it('serves the app from an https origin the API can allow', () => {
    expect(config.server.androidScheme).toBe('https')
    expect(config.server.hostname).toBe('app.intervox.site')
    expect(config.server.hostname).not.toMatch(/localhost/)
    expect(config.server.url).toBeUndefined() // bundled assets, not a live-reload server
  })

  it('bundles the Vite build', () => {
    expect(config.webDir).toBe('dist')
    expect(config.appId).toBe('site.intervox.app')
  })
})
