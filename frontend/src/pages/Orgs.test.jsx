import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from '../App'
import { AuthProvider } from '../lib/auth'

// Organizations and the sales demo (T-166).

const ORG = { id: 7, name: 'Northstar Career Partners', logo: null, color: '#1f6f8b', is_demo: true }
const ADMIN = { id: 1, name: 'Hibah', email: 'admin@example.com', is_admin: true, can_use_demo: true, orgs: [] }
const REGULAR = { id: 2, name: 'Ada', email: 'ada@example.com', is_admin: false }
const COACH = { id: 3, name: 'Morgan Ellis', is_admin: false, is_demo: true, demo_role: 'coach', orgs: [{ ...ORG, role: 'coach', consent: null }] }
const CANDIDATE = {
  id: 4,
  name: 'Alex Chen',
  is_admin: false,
  is_demo: true,
  demo_role: 'candidate',
  orgs: [{ ...ORG, role: 'candidate', consent: true }],
}

const ok = (body) => ({ ok: true, status: 200, json: async () => body })
const notFound = { ok: false, status: 404, json: async () => ({ error: 'Not found' }) }

// routes: { 'GET /api/x': body | fn(init) | Response-like }
function mockFetch(routes) {
  const calls = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url, init = {}) => {
      const key = `${init.method ?? 'GET'} ${url}`
      calls.push(key)
      const r = routes[key]
      if (r === undefined) return ok({})
      const value = typeof r === 'function' ? r(init) : r
      return value && 'ok' in value && 'status' in value ? value : ok(value)
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

afterEach(() => {
  vi.unstubAllGlobals()
  localStorage.clear()
})

const STATS = { stats: { interviews: 0, history: [] } }

describe('regular users', () => {
  it('see no Coach or Demo links and never call the org or demo APIs', async () => {
    localStorage.setItem('mi_token', 'tok')
    const calls = mockFetch({ 'GET /api/auth/me': { user: REGULAR }, 'GET /api/stats': STATS, 'GET /api/sessions': { sessions: [] } })
    renderAt('/')
    expect(await screen.findByText(/Welcome, Ada/)).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Coach' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Demo' })).not.toBeInTheDocument()
    expect(screen.queryByText('Assigned by your coach')).not.toBeInTheDocument()
    expect(calls.some((c) => c.includes('/api/orgs') || c.includes('/api/demo'))).toBe(false)
  })

  it('get Page not found at /demo and /coach, with no API calls', async () => {
    localStorage.setItem('mi_token', 'tok')
    for (const path of ['/demo', '/coach']) {
      const calls = mockFetch({ 'GET /api/auth/me': { user: REGULAR } })
      const { unmount } = renderAt(path)
      expect(await screen.findByText('Page not found.')).toBeInTheDocument()
      expect(screen.queryByText('InterVox for coaches')).not.toBeInTheDocument()
      expect(calls.some((c) => c.includes('/api/orgs') || c.includes('/api/demo'))).toBe(false)
      unmount()
    }
  })
})

describe('admin demo', () => {
  const DEMO = {
    demo: {
      seeded: true,
      org: ORG.name,
      color: ORG.color,
      logo: 'data:image/svg+xml;base64,PHN2Zy8+',
      coach: 'Morgan Ellis',
      candidates: [{ name: 'Alex Chen', role: 'Backend Software Engineer', demo_ready: true }],
    },
  }

  it('views as the demo coach, shows the Demo bar, and goes back to admin', async () => {
    localStorage.setItem('mi_token', 'admin-tok')
    let me = ADMIN
    mockFetch({
      'GET /api/auth/me': () => ok({ user: me }),
      'GET /api/admin/usage': { usage: { budget_usd: 1, month_spend_usd: 0, budget_left_usd: 1, paused: false, users_total: 1, days: [], top_users: [] } },
      'GET /api/demo': DEMO,
      'POST /api/demo/view-as': () => {
        me = COACH
        return ok({ access_token: 'demo-tok', user: COACH })
      },
      'GET /api/orgs/7/candidates': {
        org: { ...ORG, role: 'coach' },
        candidates: [
          { id: 10, name: 'Alex Chen', consent: true, role: 'Backend Software Engineer', interviews: 3, latest_score: 4.27, improvement: 1.51, trend: [2.76, 3.84, 4.27], weak_areas: [], last_interview: '2026-11-25', assignments_open: 1, needs_practice: [] },
          { id: 11, name: 'Jordan Reyes', consent: true, role: 'Customer Success Manager', interviews: 3, latest_score: 2.6, improvement: 0.45, trend: [2.15, 2.1, 2.6], weak_areas: ['Structure'], last_interview: '2026-11-17', assignments_open: 1, needs_practice: ['Low latest score'] },
          { id: 12, name: 'Pat Private', consent: false },
        ],
      },
    })
    renderAt('/admin')
    fireEvent.click(await screen.findByRole('button', { name: 'View as demo coach' }))

    expect(await screen.findByText('Your candidates')).toBeInTheDocument()
    expect(localStorage.getItem('mi_token')).toBe('demo-tok')
    expect(localStorage.getItem('mi_admin_token')).toBe('admin-tok')
    expect(screen.getByText(/Viewing as the demo coach/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Coach' })).toBeInTheDocument()
    expect(screen.getByText('Needs practice', { selector: 'span' })).toBeInTheDocument()
    expect(screen.getByText(/Waiting for consent/)).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Pat Private' })).not.toBeInTheDocument()

    me = ADMIN
    fireEvent.click(screen.getByRole('button', { name: 'Back to admin' }))
    expect(await screen.findByText('Usage and Fire spend')).toBeInTheDocument()
    expect(localStorage.getItem('mi_token')).toBe('admin-tok')
    expect(localStorage.getItem('mi_admin_token')).toBeNull()
  })

  it('shows the pitch page with the same buttons', async () => {
    localStorage.setItem('mi_token', 'admin-tok')
    mockFetch({ 'GET /api/auth/me': { user: ADMIN }, 'GET /api/demo': DEMO })
    renderAt('/demo')
    expect(await screen.findByText('InterVox for coaches')).toBeInTheDocument()
    expect(await screen.findByRole('button', { name: 'View as demo coach' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'View as demo candidate' })).toBeInTheDocument()
  })
})

describe('candidates', () => {
  it('see assignments on the dashboard, and Start is off in the demo', async () => {
    localStorage.setItem('mi_token', 'demo-tok')
    mockFetch({
      'GET /api/auth/me': { user: CANDIDATE },
      'GET /api/stats': STATS,
      'GET /api/sessions': { sessions: [] },
      'GET /api/orgs/mine': {
        orgs: CANDIDATE.orgs,
        assignments: [
          { id: 1, role_title: 'Senior Backend Engineer', duration_min: 30, due_date: '2026-11-30', status: 'todo', session_id: null, coach_name: 'Morgan Ellis' },
          { id: 2, role_title: 'Backend Software Engineer', duration_min: 30, due_date: '2026-11-20', status: 'done', session_id: 5, coach_name: 'Morgan Ellis' },
        ],
      },
    })
    renderAt('/')
    expect(await screen.findByText('Assigned by your coach')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'See report' })).toHaveAttribute('href', '/report/5')
    fireEvent.click(screen.getByRole('button', { name: 'Start' }))
    expect(await screen.findByText(/live interviews are off/)).toBeInTheDocument()
  })

  it('see their coach’s comments on their report', async () => {
    localStorage.setItem('mi_token', 'demo-tok')
    mockFetch({
      'GET /api/auth/me': { user: CANDIDATE },
      'GET /api/sessions/5/report': {
        report: {
          session_id: 5, status: 'ready', role_title: 'Backend Software Engineer', duration_min: 30, difficulty: 'mid',
          overall_score: 4.3, verdict: 'hire', verdict_reason: 'Strong.', takeaways: [], exercises: [], competencies: [],
          unanswered: [], questions: [], progress: { scored: 0, total: 0 }, analytics: null,
        },
      },
      'GET /api/orgs/mine/sessions/5/comments': {
        comments: [{ id: 1, body: 'Open with the incident story.', author: 'Morgan Ellis', created_at: '2026-11-25T10:00:00Z' }],
      },
    })
    renderAt('/report/5')
    expect(await screen.findByText('From your coach')).toBeInTheDocument()
    expect(screen.getByText('Open with the incident story.')).toBeInTheDocument()
  })

  it('join by invite and choose separately to share reports', async () => {
    localStorage.setItem('mi_token', 'tok')
    const consent = vi.fn(() => ok({ consent: true }))
    mockFetch({
      'GET /api/auth/me': { user: { ...REGULAR, orgs: [] } },
      'GET /api/orgs/invites/abc': { org: { ...ORG, is_demo: false }, member: false },
      'POST /api/orgs/invites/abc/accept': { org: ORG, role: 'candidate', consent: false },
      'PUT /api/orgs/7/consent': consent,
    })
    renderAt('/join/abc')
    fireEvent.click(await screen.findByRole('button', { name: `Join ${ORG.name}` }))
    const box = await screen.findByRole('checkbox', { name: /Share my interview reports/ })
    expect(box).not.toBeChecked()
    fireEvent.click(box)
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(consent).toHaveBeenCalled())
    expect(JSON.parse(consent.mock.calls[0][0].body)).toEqual({ share: true })
  })

  it('shows an expired invite plainly', async () => {
    localStorage.setItem('mi_token', 'tok')
    mockFetch({ 'GET /api/auth/me': { user: { ...REGULAR, orgs: [] } }, 'GET /api/orgs/invites/old': notFound })
    renderAt('/join/old')
    expect(await screen.findByRole('alert')).toHaveTextContent('invalid or has expired')
  })
})
