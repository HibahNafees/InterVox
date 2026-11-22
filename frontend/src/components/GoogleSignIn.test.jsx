// Sign in with Google (T-156): website button and the Android app's native picker.
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../App'
import { AuthProvider } from '../lib/auth'
import { isNativeApp } from '../lib/native'

vi.mock('../lib/native', () => ({ isNativeApp: vi.fn(() => false) }))
const login = vi.fn()
vi.mock('@capgo/capacitor-social-login', () => ({
  SocialLogin: { initialize: vi.fn(async () => {}), login: (...args) => login(...args) },
}))

const GRACE = { id: 2, name: 'Grace', email: 'grace@example.com', has_password: false, google: true }
const CLIENT = 'web-123.apps.googleusercontent.com'

function respond(routes) {
  const calls = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url, opts = {}) => {
      const key = `${opts.method || 'GET'} ${url}`
      calls.push({ key, opts })
      const hit = routes[key]
      if (!hit) throw new Error(`unexpected ${key}`)
      const [status, body] = hit
      return { ok: status < 400, status, json: async () => body }
    }),
  )
  return calls
}

function renderAt(path) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <App />
      </AuthProvider>
    </MemoryRouter>,
  )
}

// Google's script, already loaded: records the button and lets a test "pick" an account.
function fakeGis() {
  const gis = { initialize: vi.fn(), renderButton: vi.fn() }
  vi.stubGlobal('google', { accounts: { id: gis } })
  return {
    gis,
    pick: (credential) => gis.initialize.mock.calls.at(-1)[0].callback({ credential }),
  }
}

beforeEach(() => localStorage.clear())
afterEach(() => {
  vi.unstubAllGlobals()
  isNativeApp.mockReturnValue(false)
})

describe('Sign in with Google', () => {
  it('stays hidden when the API has no Google client id', async () => {
    const calls = respond({ 'GET /api/auth/providers': [200, { google_client_id: null }] })
    renderAt('/signup')
    await vi.waitFor(() => expect(calls.some((c) => c.key === 'GET /api/auth/providers')).toBe(true))
    expect(screen.queryByTestId('google-button')).not.toBeInTheDocument()
    expect(screen.queryByText(/or with email/i)).not.toBeInTheDocument()
  })

  it('signs up from the website button without a password', async () => {
    const { gis, pick } = fakeGis()
    const calls = respond({
      'GET /api/auth/providers': [200, { google_client_id: CLIENT }],
      'POST /api/auth/google': [201, { access_token: 'tok-g', user: GRACE }],
      'GET /api/stats': [200, {}],
      'GET /api/sessions': [200, { sessions: [] }],
      'GET /api/documents': [200, { documents: [] }],
    })
    renderAt('/signup')
    await screen.findByTestId('google-button')
    await vi.waitFor(() => expect(gis.renderButton).toHaveBeenCalled())
    expect(gis.initialize.mock.calls[0][0].client_id).toBe(CLIENT)
    await pick('google-id-token')
    const post = calls.find((c) => c.key === 'POST /api/auth/google')
    expect(JSON.parse(post.opts.body)).toEqual({ credential: 'google-id-token' })
    expect(localStorage.getItem('mi_token')).toBe('tok-g')
  })

  it("shows the API's refusal", async () => {
    const { gis, pick } = fakeGis()
    respond({
      'GET /api/auth/providers': [200, { google_client_id: CLIENT }],
      'POST /api/auth/google': [401, { error: "That Google account's email isn't verified yet." }],
    })
    renderAt('/login')
    await vi.waitFor(() => expect(gis.renderButton).toHaveBeenCalled())
    await pick('google-id-token')
    expect(await screen.findByRole('alert')).toHaveTextContent('email isn')
  })

  it('uses the native account picker in the Android app', async () => {
    isNativeApp.mockReturnValue(true)
    login.mockResolvedValue({ provider: 'google', result: { idToken: 'native-id-token' } })
    const calls = respond({
      'GET /api/auth/providers': [200, { google_client_id: CLIENT }],
      'POST /api/auth/google': [200, { access_token: 'tok-n', user: GRACE }],
      'GET /api/stats': [200, {}],
      'GET /api/sessions': [200, { sessions: [] }],
      'GET /api/documents': [200, { documents: [] }],
    })
    renderAt('/login')
    await userEvent.click(await screen.findByRole('button', { name: 'Continue with Google' }))
    await vi.waitFor(() => expect(localStorage.getItem('mi_token')).toBe('tok-n'))
    expect(login).toHaveBeenCalledWith({ provider: 'google', options: {} })
    const post = calls.find((c) => c.key === 'POST /api/auth/google')
    expect(JSON.parse(post.opts.body)).toEqual({ credential: 'native-id-token' })
  })

  it('does nothing when the Android picker is cancelled', async () => {
    isNativeApp.mockReturnValue(true)
    login.mockRejectedValue(new Error('User cancelled the selector'))
    const calls = respond({ 'GET /api/auth/providers': [200, { google_client_id: CLIENT }] })
    renderAt('/login')
    await userEvent.click(await screen.findByRole('button', { name: 'Continue with Google' }))
    await screen.findByRole('button', { name: 'Continue with Google' })
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(calls.some((c) => c.key === 'POST /api/auth/google')).toBe(false)
  })
})
