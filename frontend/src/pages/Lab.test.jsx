import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from '../App'
import { AuthProvider } from '../lib/auth'

const ADA = { id: 1, name: 'Ada', email: 'ada@example.com' }
const DEFAULTS = {
  model: 'gpt-4o-mini',
  models: [
    { id: 'gpt-4o-mini', label: 'GPT-4o mini (cheapest)', max_temperature: 1 },
    { id: 'claude-haiku-4-5', label: 'Claude Haiku 4.5', max_temperature: 1 },
  ],
  agents: {
    prep: { system: 'You are a coach.', temperature: 0.5 },
    advocate: { system: 'Argue for.', temperature: 1 },
    skeptic: { system: 'Argue against.', temperature: 1 },
    judge: { system: 'Judge fairly.', temperature: 0 },
  },
  costs: { chat: 1, compare: 2, debate: 3 },
}

function respond(routes) {
  const calls = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url, opts = {}) => {
      const key = `${opts.method || 'GET'} ${url}`
      calls.push({ key, body: opts.body ? JSON.parse(opts.body) : undefined })
      const hit = routes[key]
      if (!hit) throw new Error(`unexpected ${key}`)
      const [status, body] = typeof hit === 'function' ? hit(opts) : hit
      return { ok: status < 400, status, json: async () => body }
    }),
  )
  return calls
}

function base(used = 0, extra = {}) {
  return {
    'GET /api/auth/me': [200, { user: ADA }],
    'GET /api/lab': [200, { defaults: DEFAULTS, usage: { used, cap: 10 } }],
    'GET /api/documents?kind=resume': [200, { documents: [] }],
    'GET /api/documents?kind=job_description': [200, { documents: [] }],
    ...extra,
  }
}

function renderLab() {
  localStorage.setItem('mi_token', 'tok')
  render(
    <MemoryRouter initialEntries={['/lab']}>
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

describe('Chat Lab', () => {
  it('chats with the prep coach and shows calls used today', async () => {
    const calls = respond(
      base(0, { 'POST /api/lab/chat': [200, { reply: 'Expect a STAR question.', usage: { used: 1, cap: 10 } }] }),
    )
    renderLab()
    expect(await screen.findByText(/0 of 10 Chat Lab calls used today/)).toBeInTheDocument()
    await userEvent.type(screen.getByLabelText('Message'), 'What will they ask?')
    await userEvent.click(screen.getByRole('button', { name: /Send/ }))
    expect(await screen.findByText('Expect a STAR question.')).toBeInTheDocument()
    expect(screen.getByText(/1 of 10 Chat Lab calls used today/)).toBeInTheDocument()
    const sent = calls.find((c) => c.key === 'POST /api/lab/chat').body
    expect(sent.messages).toEqual([{ role: 'user', content: 'What will they ask?' }])
    expect(sent.settings.model).toBe('gpt-4o-mini')
  })

  it('shows the debate, the score out of 5 and the practice note', async () => {
    respond(
      base(0, {
        'POST /api/lab/debate': [
          200,
          {
            for: 'Strong ownership.',
            against: 'No result.',
            verdict: { score: 3, reasons: ['Clear story.'], tip: 'Add a number.' },
            usage: { used: 3, cap: 10 },
          },
        ],
      }),
    )
    renderLab()
    await userEvent.click(await screen.findByRole('tab', { name: 'Debate' }))
    await userEvent.type(screen.getByLabelText('Interview question'), 'Lead a project?')
    await userEvent.type(screen.getByLabelText('Your answer'), 'I led billing.')
    await userEvent.click(screen.getByRole('button', { name: /Start the debate/ }))
    expect(await screen.findByText('Strong ownership.')).toBeInTheDocument()
    expect(screen.getByText('No result.')).toBeInTheDocument()
    expect(screen.getByText('Add a number.')).toBeInTheDocument()
    expect(screen.getByText(/not a hiring decision/)).toBeInTheDocument()
  })

  it('disables a debate when fewer than 3 calls are left', async () => {
    respond(base(8))
    renderLab()
    await userEvent.click(await screen.findByRole('tab', { name: 'Debate' }))
    await userEvent.type(screen.getByLabelText('Interview question'), 'Q?')
    await userEvent.type(screen.getByLabelText('Your answer'), 'A.')
    expect(screen.getByRole('button', { name: /Start the debate/ })).toBeDisabled()
  })

  it('edits settings, remembers them, and resets', async () => {
    const calls = respond(
      base(0, { 'POST /api/lab/chat': [200, { reply: 'Ok.', usage: { used: 1, cap: 10 } }] }),
    )
    renderLab()
    await userEvent.click(await screen.findByRole('tab', { name: 'Settings' }))
    const prompts = screen.getAllByLabelText('System prompt')
    await userEvent.clear(prompts[0])
    await userEvent.type(prompts[0], 'Be brief.')
    expect(JSON.parse(localStorage.getItem('intervox_lab_settings')).agents.prep.system).toBe('Be brief.')
    await userEvent.click(screen.getByRole('tab', { name: 'Prep chat' }))
    await userEvent.type(screen.getByLabelText('Message'), 'Hi')
    await userEvent.click(screen.getByRole('button', { name: /Send/ }))
    await screen.findByText('Ok.')
    expect(calls.find((c) => c.key === 'POST /api/lab/chat').body.settings.agents.prep.system).toBe('Be brief.')
    await userEvent.click(screen.getByRole('tab', { name: 'Settings' }))
    await userEvent.click(screen.getByRole('button', { name: 'Reset to defaults' }))
    expect(screen.getAllByLabelText('System prompt')[0]).toHaveValue('You are a coach.')
    expect(localStorage.getItem('intervox_lab_settings')).toBeNull()
  })
})
