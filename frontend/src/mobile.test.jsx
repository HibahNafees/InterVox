// Phones, the installable web app and the Android app (T-149, T-150).
import { readFileSync } from 'node:fs'
import { cwd } from 'node:process'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import CodePad from './components/CodePad'
import { DialogProvider } from './components/ConfirmDialog'
import InstallApp from './components/InstallApp'
import Layout from './components/Layout'
import { AuthProvider } from './lib/auth'
import { isNativeApp } from './lib/native'
import { listenForInstall, registerServiceWorker } from './lib/pwa'

vi.mock('./lib/native', () => ({ isNativeApp: vi.fn(() => false) }))

const ADA = { id: 1, name: 'Ada', email: 'ada@example.com' }

function phone(small = true) {
  vi.stubGlobal('matchMedia', (query) => ({
    matches: query === '(max-width: 639px)' ? small : false,
    addEventListener() {},
    removeEventListener() {},
  }))
}

function respond(routes) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url, opts = {}) => {
      const key = `${opts.method || 'GET'} ${url}`
      const hit = routes[key]
      if (!hit) return { ok: false, status: 404, json: async () => ({ error: 'Not found' }) }
      const [status, body] = typeof hit === 'function' ? hit(opts) : hit
      return { ok: status < 400, status, json: async () => body }
    }),
  )
}

beforeEach(() => localStorage.setItem('mi_token', 'tok'))
afterEach(() => {
  vi.unstubAllGlobals()
  isNativeApp.mockReturnValue(false)
})

describe('service worker', () => {
  // public/sw.js runs as a classic worker script; load its filter function here.
  const source = readFileSync(`${cwd()}/public/sw.js`, 'utf8')
  const fakeSelf = { addEventListener() {}, location: { origin: 'https://www.intervox.site' } }
  const shouldCache = new Function('self', 'caches', 'fetch', `${source}\nreturn shouldCache`)(fakeSelf, {}, () => {})
  const ok = (url, method = 'GET') => shouldCache({ url, method }, 'https://www.intervox.site')

  it('caches the app shell only', () => {
    expect(ok('https://www.intervox.site/assets/index-abc.js')).toBe(true)
    expect(ok('https://www.intervox.site/icons/icon-192.png')).toBe(true)
    expect(ok('https://www.intervox.site/manifest.webmanifest')).toBe(true)
  })

  it('never caches API calls, user data, shared reports or other sites', () => {
    expect(ok('https://intervox.duckdns.org/api/sessions')).toBe(false)
    expect(ok('https://www.intervox.site/api/auth/me')).toBe(false)
    expect(ok('https://www.intervox.site/shared/abc123')).toBe(false)
    expect(ok('https://www.intervox.site/assets/index-abc.js', 'POST')).toBe(false)
    expect(ok('https://fonts.googleapis.com/css2?family=x')).toBe(false)
    expect(ok('https://www.intervox.site/articles/ai-interviewer.html')).toBe(false)
  })

  it('registers on the website only, never in dev or the Android app', () => {
    vi.stubGlobal('navigator', { ...navigator, serviceWorker: { register: vi.fn(async () => ({})) } })
    expect(registerServiceWorker({ prod: false })).toBe(false)
    isNativeApp.mockReturnValue(true)
    expect(registerServiceWorker({ prod: true })).toBe(false)
    isNativeApp.mockReturnValue(false)
    expect(registerServiceWorker({ prod: true })).toBe(true)
  })
})

describe('install prompt', () => {
  it('offers to install when the browser allows it, and remembers "Not now"', async () => {
    phone(false)
    listenForInstall()
    const prompt = vi.fn(async () => ({ outcome: 'accepted' }))
    const view = () =>
      render(
        <DialogProvider>
          <InstallApp />
        </DialogProvider>,
      )
    const { unmount } = view()
    expect(screen.queryByRole('button', { name: /Install app/ })).not.toBeInTheDocument()
    window.dispatchEvent(Object.assign(new Event('beforeinstallprompt'), { prompt }))
    await userEvent.click(await screen.findByRole('button', { name: /Install app/ }))
    expect(prompt).toHaveBeenCalled()
    unmount()

    window.dispatchEvent(Object.assign(new Event('beforeinstallprompt'), { prompt }))
    view()
    await userEvent.click(await screen.findByRole('button', { name: 'Not now' }))
    expect(screen.queryByRole('button', { name: /Install app/ })).not.toBeInTheDocument()
    expect(localStorage.getItem('mi_install_dismissed')).toBe('1')
  })

  it('never shows inside the Android app', () => {
    phone(false)
    isNativeApp.mockReturnValue(true)
    window.dispatchEvent(Object.assign(new Event('beforeinstallprompt'), { prompt: vi.fn() }))
    render(
      <DialogProvider>
        <InstallApp />
      </DialogProvider>,
    )
    expect(screen.queryByRole('button', { name: /Install app/ })).not.toBeInTheDocument()
  })
})

describe('phone layout', () => {
  it('folds the nav behind a Menu button that closes after moving', async () => {
    phone()
    respond({ 'GET /api/auth/me': [200, { user: ADA }] })
    render(
      <MemoryRouter initialEntries={['/']}>
        <AuthProvider>
          <DialogProvider>
            <Routes>
              <Route element={<Layout />}>
                <Route path="/" element={<p>Home page</p>} />
                <Route path="/stories" element={<p>Stories page</p>} />
              </Route>
            </Routes>
          </DialogProvider>
        </AuthProvider>
      </MemoryRouter>,
    )
    const menu = await screen.findByRole('button', { name: 'Menu' })
    expect(menu).toHaveAttribute('aria-expanded', 'false')
    expect(screen.getByRole('navigation', { name: 'Main' })).toHaveClass('hidden')
    await userEvent.click(menu)
    expect(screen.getByRole('button', { name: 'Close' })).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByRole('navigation', { name: 'Main' })).not.toHaveClass('hidden')
    await userEvent.click(screen.getByRole('link', { name: 'Story bank' }))
    expect(await screen.findByText('Stories page')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Menu' })).toHaveAttribute('aria-expanded', 'false')
  })

  it('leaves coding and whiteboard rounds out of setup on a phone', async () => {
    phone()
    let created
    let nextDoc = 10
    const mod = (name, label) => ({ name, label, blurb: `${label} questions.` })
    respond({
      'GET /api/auth/me': [200, { user: ADA }],
      'GET /api/documents?kind=resume': [200, { documents: [] }],
      'GET /api/documents?kind=job_description': [200, { documents: [] }],
      'POST /api/documents': (opts) => [201, { document: { id: nextDoc++, kind: JSON.parse(opts.body).kind, title: 'x' } }],
      'POST /api/documents/11/analysis': [
        200,
        {
          analysis: { role_title: 'Backend Engineer', field: 'software', competencies: [] },
          modules: [mod('behavioral', 'Behavioral'), mod('coding', 'Coding'), mod('system_design', 'System design')],
        },
      ],
      'GET /api/stories/suggest?jd_id=11': [200, { stories: [] }],
      'POST /api/sessions': (opts) => {
        created = JSON.parse(opts.body)
        return [201, { session: { id: 7, status: 'planned' } }]
      },
    })
    render(
      <MemoryRouter initialEntries={['/setup']}>
        <AuthProvider>
          <App />
        </AuthProvider>
      </MemoryRouter>,
    )
    const long = 'x'.repeat(60)
    await userEvent.type(await screen.findByLabelText('Paste your résumé'), long)
    await userEvent.click(screen.getAllByRole('button', { name: 'Use this text' })[0])
    await userEvent.type(screen.getByLabelText('Paste job description'), long)
    await userEvent.click(screen.getByRole('button', { name: 'Use this text' }))
    expect(await screen.findByRole('radio', { name: 'Behavioral' })).toBeInTheDocument()
    expect(screen.queryByRole('radio', { name: 'Coding' })).not.toBeInTheDocument()
    expect(screen.queryByRole('radio', { name: 'System design' })).not.toBeInTheDocument()
    expect(screen.queryByText('Hands-on rounds')).not.toBeInTheDocument()
    expect(screen.getByText(/need a bigger screen/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Build my interview plan' }))
    await vi.waitFor(() => expect(created).toMatchObject({ coding_problems: 0, system_design: 0 }))
  })

  it('gives the plain code box on a phone, without the full editor', () => {
    phone()
    render(<CodePad code={{ language: 'python', content: '' }} onChange={() => {}} />)
    expect(screen.getByLabelText('Your code')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Use the code editor' })).not.toBeInTheDocument()
  })
})
