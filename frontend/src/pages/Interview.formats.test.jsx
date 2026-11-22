import { fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from '../App'
import { AuthProvider } from '../lib/auth'

const ADA = { id: 1, name: 'Ada', email: 'ada@example.com' }
const TIMER = {
  total_sec: 600,
  elapsed_sec: 0,
  remaining_sec: 600,
  section: 'Background',
  section_budget_sec: 240,
  section_elapsed_sec: 0,
  section_remaining_sec: 240,
}
const PANEL = [
  { key: 'hm', name: 'Priya', title: 'the hiring manager' },
  { key: 'peer', name: 'Marcus', title: 'a senior colleague on the team' },
]

function respond(routes) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url, opts = {}) => {
      const key = `${opts.method || 'GET'} ${url}`
      const hit = Object.entries(routes).find(([k]) => key === k)
      if (!hit) throw new Error(`unexpected ${key}`)
      const [status, body] = typeof hit[1] === 'function' ? hit[1](opts) : hit[1]
      return { ok: status < 400, status, json: async () => body }
    }),
  )
}

function renderAt(path) {
  localStorage.setItem('mi_token', 'tok')
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <App />
      </AuthProvider>
    </MemoryRouter>,
  )
}

afterEach(() => vi.unstubAllGlobals())

describe('formats', () => {
  it('sets up a salary negotiation and starts the call at once', async () => {
    let created
    let nextDoc = 10
    const negotiation = { offer: '$80,000', target: '$92,000', company: '' }
    const active = {
      id: 7,
      status: 'active',
      mode: 'negotiation',
      role_title: 'Backend Engineer',
      duration_min: 10,
      persona: 'neutral',
      negotiation,
      plan: {
        sections: [
          {
            name: 'Offer negotiation',
            module: 'roleplay',
            minutes: 10,
            questions: ['Hi Ada, it’s Sam.'],
            scenario: { character: 'Sam, the recruiter', setting: '', goal: 'negotiate a better offer than $80,000' },
          },
        ],
        reserve: [],
      },
      timer: { ...TIMER, section: 'Offer negotiation' },
      transcript: [
        {
          question_id: 1,
          section: 'Offer negotiation',
          interviewer: 'Hi Ada, it’s Sam.',
          segments: [{ who: 'character', text: 'Hi Ada, it’s Sam.' }],
          answer: null,
        },
      ],
    }
    respond({
      'GET /api/auth/me': [200, { user: ADA }],
      'GET /api/documents?kind=resume': [200, { documents: [] }],
      'GET /api/documents?kind=job_description': [200, { documents: [] }],
      'POST /api/documents': (opts) => [
        201,
        { document: { id: nextDoc++, kind: JSON.parse(opts.body).kind, title: 'x' } },
      ],
      'POST /api/documents/11/analysis': [
        200,
        { analysis: { role_title: 'Backend Engineer', field: 'software', competencies: [] }, modules: [] },
      ],
      'GET /api/stories/suggest?jd_id=11': [200, { stories: [] }],
      'POST /api/sessions': (opts) => {
        created = JSON.parse(opts.body)
        return [201, { session: { ...active, status: 'planned' } }]
      },
      'POST /api/sessions/7/start': [200, { session: active, speech: null }],
      'GET /api/sessions/7': [200, { session: active }],
    })
    renderAt('/setup')
    const long = 'x'.repeat(60)
    await userEvent.type(await screen.findByLabelText('Paste your résumé'), long)
    await userEvent.click(screen.getAllByRole('button', { name: 'Use this text' })[0])
    await userEvent.type(screen.getByLabelText('Paste job description'), long)
    await userEvent.click(screen.getByRole('button', { name: 'Use this text' }))
    await userEvent.click(await screen.findByRole('radio', { name: '💰 Salary negotiation' }))
    // No pressure, interview type or plan review for a negotiation.
    expect(screen.queryByRole('radiogroup', { name: 'Pressure' })).not.toBeInTheDocument()
    expect(screen.queryByRole('radiogroup', { name: 'Interview type' })).not.toBeInTheDocument()
    expect(screen.queryByRole('radio', { name: '60 min' })).not.toBeInTheDocument()
    const startCall = screen.getByRole('button', { name: 'Start the call' })
    expect(startCall).toBeDisabled()
    await userEvent.type(screen.getByPlaceholderText('e.g. $80,000 base'), '$80,000')
    await userEvent.type(screen.getByPlaceholderText('e.g. $92,000'), '$92,000')
    await userEvent.click(startCall)
    expect(await screen.findByText(/\(you're aiming for/)).toHaveTextContent('Negotiation:')
    expect(screen.getByText('$92,000')).toBeInTheDocument()
    expect(created).toMatchObject({ format: 'negotiation', negotiation, duration_min: 10, pressure_level: 0 })
  })

  it('labels each panel interviewer', async () => {
    const session = {
      id: 8,
      status: 'active',
      mode: 'panel',
      role_title: 'Backend Engineer',
      duration_min: 10,
      persona: 'neutral',
      panel: PANEL,
      plan: { sections: [], reserve: [] },
      timer: TIMER,
      transcript: [
        {
          question_id: 1,
          section: 'Background',
          interviewer: 'Hello Ada.',
          segments: [{ who: 'interviewer', panelist: 'hm', text: 'Hello Ada. Tell me about Acme.' }],
          answer: 'I built the billing API.',
        },
        {
          question_id: 2,
          section: 'Technical',
          interviewer: '…',
          segments: [
            { who: 'interviewer', panelist: 'hm', text: "Thanks. I'll hand over to Marcus now." },
            { who: 'interviewer', panelist: 'peer', text: 'Hi, Marcus here. Design a rate limiter.' },
          ],
          answer: null,
        },
      ],
    }
    respond({
      'GET /api/auth/me': [200, { user: ADA }],
      'GET /api/sessions/8': [200, { session }],
    })
    renderAt('/interview/8')
    expect(await screen.findByText('Hi, Marcus here. Design a rate limiter.')).toBeInTheDocument()
    expect(screen.getAllByText('Priya · hiring manager')).toHaveLength(2)
    expect(screen.getByText('Marcus · senior colleague on the team')).toBeInTheDocument()
  })
})

describe('setup choices for hands-on rounds and pressure', () => {
  it('asks how many coding problems and keeps a panel with pressure', async () => {
    let created
    let nextDoc = 10
    respond({
      'GET /api/auth/me': [200, { user: ADA }],
      'GET /api/documents?kind=resume': [200, { documents: [] }],
      'GET /api/documents?kind=job_description': [200, { documents: [] }],
      'POST /api/documents': (opts) => [
        201,
        { document: { id: nextDoc++, kind: JSON.parse(opts.body).kind, title: 'x' } },
      ],
      'POST /api/documents/11/analysis': [
        200,
        {
          analysis: { role_title: 'Software Developer', field: 'software engineering', competencies: [] },
          modules: [
            { name: 'technical', label: 'Technical Q&A', blurb: '' },
            { name: 'coding', label: 'Coding', blurb: '' },
            { name: 'system_design', label: 'System design', blurb: '' },
          ],
        },
      ],
      'GET /api/stories/suggest?jd_id=11': [200, { stories: [] }],
      'POST /api/sessions': (opts) => {
        created = JSON.parse(opts.body)
        return [400, { error: 'stop here' }]
      },
    })
    renderAt('/setup')
    const long = 'x'.repeat(60)
    await userEvent.type(await screen.findByLabelText('Paste your résumé'), long)
    await userEvent.click(screen.getAllByRole('button', { name: 'Use this text' })[0])
    await userEvent.type(screen.getByLabelText('Paste job description'), long)
    await userEvent.click(screen.getByRole('button', { name: 'Use this text' }))
    const coding = await screen.findByRole('radiogroup', { name: 'Coding problems' })
    await userEvent.click(within(coding).getByRole('radio', { name: 'Custom' }))
    fireEvent.change(screen.getByLabelText('Coding problems: how many'), { target: { value: '10' } })
    // 10 problems need 40+ minutes: blocked with a reason until it fits.
    expect(screen.getByRole('alert')).toHaveTextContent('10 coding problems (4+ min each) need at least 40 minutes')
    expect(screen.getByRole('button', { name: 'Build my interview plan' })).toBeDisabled()
    await userEvent.click(screen.getByRole('radio', { name: '30 min' }))
    fireEvent.change(screen.getByLabelText('Coding problems: how many'), { target: { value: '5' } })
    expect(screen.queryByText(/need at least/)).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('radio', { name: 'Skip it' }))
    // A panel and a pressure level go together, in either order (T-132).
    await userEvent.click(screen.getByRole('radio', { name: '4 · 45 s + curveballs' }))
    await userEvent.click(screen.getByRole('radio', { name: '👥 Panel' }))
    expect(screen.getByRole('radio', { name: '4 · 45 s + curveballs' })).toBeChecked()
    await userEvent.click(screen.getByRole('radio', { name: '2 · Pushback' }))
    expect(screen.getByRole('radio', { name: '👥 Panel' })).toBeChecked()
    await userEvent.click(screen.getByRole('button', { name: 'Build my interview plan' }))
    await screen.findByText('stop here')
    expect(created).toMatchObject({
      format: 'panel',
      pressure_level: 2,
      coding_problems: 5,
      system_design: 0,
      duration_min: 30,
    })
  })

  it('keeps hands-on rounds for a single interview type (T-95)', async () => {
    let created
    let nextDoc = 10
    respond({
      'GET /api/auth/me': [200, { user: ADA }],
      'GET /api/documents?kind=resume': [200, { documents: [] }],
      'GET /api/documents?kind=job_description': [200, { documents: [] }],
      'POST /api/documents': (opts) => [
        201,
        { document: { id: nextDoc++, kind: JSON.parse(opts.body).kind, title: 'x' } },
      ],
      'POST /api/documents/11/analysis': [
        200,
        {
          analysis: { role_title: 'Software Developer', field: 'software engineering', competencies: [] },
          modules: [
            { name: 'behavioral', label: 'Behavioral', blurb: '' },
            { name: 'coding', label: 'Coding', blurb: '' },
            { name: 'system_design', label: 'System design', blurb: '' },
          ],
        },
      ],
      'GET /api/stories/suggest?jd_id=11': [200, { stories: [] }],
      'POST /api/sessions': (opts) => {
        created = JSON.parse(opts.body)
        return [400, { error: 'stop here' }]
      },
    })
    renderAt('/setup')
    const long = 'x'.repeat(60)
    await userEvent.type(await screen.findByLabelText('Paste your résumé'), long)
    await userEvent.click(screen.getAllByRole('button', { name: 'Use this text' })[0])
    await userEvent.type(screen.getByLabelText('Paste job description'), long)
    await userEvent.click(screen.getByRole('button', { name: 'Use this text' }))
    const type = await screen.findByRole('radiogroup', { name: 'Interview type' })
    await userEvent.click(within(type).getByRole('radio', { name: 'Behavioral' }))
    const coding = screen.getByRole('radiogroup', { name: 'Coding problems' })
    expect(screen.getByRole('radiogroup', { name: 'System design' })).toBeInTheDocument()
    expect(screen.getAllByText('Only Behavioral questions unless you pick a number.')).toHaveLength(2)
    await userEvent.click(screen.getByRole('radio', { name: '30 min' }))
    await userEvent.click(within(coding).getByRole('radio', { name: '2' }))
    await userEvent.click(screen.getByRole('button', { name: 'Build my interview plan' }))
    await screen.findByText('stop here')
    expect(created).toMatchObject({ focus: 'behavioral', coding_problems: 2 })
    expect(created).not.toHaveProperty('system_design')
  })
})
