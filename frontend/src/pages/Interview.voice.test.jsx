import { act, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../App'
import { AuthProvider } from '../lib/auth'
import { FILLERS } from '../lib/voice'
import { fakeSpeech } from '../test-speech'

// The reply is spoken once the line before it (a filler) has finished.
async function spokenLast(spoken, text) {
  await vi.waitFor(() => expect(spoken.at(-1)?.text).toBe(text), { timeout: 3000 })
}

// Stand-in recorder: one click "records" a 4.2-second clip.
vi.mock('../components/Recorder', () => ({
  default: ({ onRecorded, disabled, autoStartKey = 0 }) => (
    <>
      <button
        type="button"
        disabled={disabled}
        onClick={() => onRecorded(new Blob(['clip'], { type: 'audio/webm;codecs=opus' }), 4200)}
      >
        Record answer
      </button>
      <span data-testid="auto-record">{autoStartKey}</span>
    </>
  ),
}))

const ADA = { id: 1, name: 'Ada', email: 'ada@example.com' }
const FIRST = {
  question_id: 1,
  interviewer: 'Tell me about Acme.',
  segments: [{ who: 'interviewer', text: 'Tell me about Acme.' }],
  answer: null,
}
const TURN = {
  action: 'follow_up',
  message: 'What was your part?',
  segments: [{ who: 'interviewer', text: 'What was your part?' }],
}
const ACTIVE = {
  id: 7,
  status: 'active',
  role_title: 'Backend Engineer',
  duration_min: 10,
  timer: { remaining_sec: 600, section: 'Background', section_remaining_sec: 240 },
  transcript: [FIRST],
}

function respond(routes) {
  const calls = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url, opts = {}) => {
      calls.push({ key: `${opts.method || 'GET'} ${url}`, opts })
      const handler = routes[`${opts.method || 'GET'} ${url}`]
      if (!handler) throw new Error(`unexpected ${url}`)
      const [status, body] = typeof handler === 'function' ? handler(opts) : handler
      return { ok: status < 400, status, json: async () => body }
    }),
  )
  return calls
}

function renderInterview() {
  localStorage.setItem('mi_token', 'tok')
  render(
    <MemoryRouter initialEntries={['/interview/7']}>
      <AuthProvider>
        <App />
      </AuthProvider>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.stubGlobal('MediaRecorder', class {})
  Object.defineProperty(navigator, 'mediaDevices', {
    configurable: true,
    value: { getUserMedia: vi.fn() },
  })
})
afterEach(() => vi.unstubAllGlobals())

describe('spoken answers', () => {
  it('transcribes the clip, then sends the text as a voice turn', async () => {
    const calls = respond({
      'GET /api/auth/me': [200, { user: ADA }],
      'GET /api/sessions/7': [200, { session: ACTIVE }],
      'POST /api/sessions/7/transcribe': [200, { text: 'I led the billing API.' }],
      'POST /api/sessions/7/turns': [
        200,
        {
          turn: TURN,
          session: {
            ...ACTIVE,
            transcript: [
              { ...FIRST, answer: 'I led the billing API.', input_mode: 'voice' },
              { question_id: 2, interviewer: 'What was your part?', answer: null },
            ],
          },
        },
      ],
    })
    renderInterview()
    await userEvent.click(await screen.findByRole('button', { name: 'Record answer' }))

    expect(await screen.findByText('What was your part?')).toBeInTheDocument()
    expect(screen.getByText('I led the billing API.')).toBeInTheDocument()
    expect(screen.getByText('You · transcribed')).toBeInTheDocument()

    const upload = calls.find((c) => c.key === 'POST /api/sessions/7/transcribe')
    expect(upload.opts.body).toBeInstanceOf(FormData)
    expect(upload.opts.body.get('audio').name).toBe('answer.webm')
    expect(upload.opts.headers['Content-Type']).toBeUndefined()
    const turn = calls.find((c) => c.key === 'POST /api/sessions/7/turns')
    expect(JSON.parse(turn.opts.body)).toEqual({
      text: 'I led the billing API.',
      duration_ms: 4200,
      input_mode: 'voice',
    })
  })

  it('keeps the transcript to resend if the interviewer call fails', async () => {
    let attempts = 0
    const calls = respond({
      'GET /api/auth/me': [200, { user: ADA }],
      'GET /api/sessions/7': [200, { session: ACTIVE }],
      'POST /api/sessions/7/transcribe': [200, { text: 'I led the billing API.' }],
      'POST /api/sessions/7/turns': () =>
        ++attempts === 1
          ? [429, { error: 'The AI service is busy; please wait a moment' }]
          : [200, { turn: TURN, session: { ...ACTIVE, transcript: [{ ...FIRST, answer: 'ok' }] } }],
    })
    renderInterview()
    await userEvent.click(await screen.findByRole('button', { name: 'Record answer' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('busy')
    expect(screen.getByLabelText('Your answer')).toHaveValue('I led the billing API.')
    await userEvent.click(screen.getByRole('button', { name: 'Send answer' }))

    const turns = calls.filter((c) => c.key === 'POST /api/sessions/7/turns')
    expect(JSON.parse(turns[1].opts.body)).toEqual({
      text: 'I led the billing API.',
      duration_ms: 4200,
      input_mode: 'voice',
    })
    expect(calls.filter((c) => c.key.endsWith('/transcribe'))).toHaveLength(1)
  })

  it('shows a transcription error and lets the user record again', async () => {
    respond({
      'GET /api/auth/me': [200, { user: ADA }],
      'GET /api/sessions/7': [200, { session: ACTIVE }],
      'POST /api/sessions/7/transcribe': [422, { error: "We didn't catch any speech; please try again" }],
    })
    renderInterview()
    await userEvent.click(await screen.findByRole('button', { name: 'Record answer' }))
    expect(await screen.findByRole('alert')).toHaveTextContent("didn't catch")
    expect(screen.getByRole('button', { name: 'Record answer' })).toBeEnabled()
  })

  it('can switch to typing', async () => {
    respond({
      'GET /api/auth/me': [200, { user: ADA }],
      'GET /api/sessions/7': [200, { session: ACTIVE }],
    })
    renderInterview()
    await userEvent.click(await screen.findByRole('button', { name: 'Type instead' }))
    expect(screen.getByLabelText('Your answer')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Speak instead' }))
    expect(screen.getByRole('button', { name: 'Record answer' })).toBeInTheDocument()
  })
})

describe('interviewer voice', () => {
  const NEXT = { question_id: 2, interviewer: 'What was your part?', segments: TURN.segments, answer: null }
  const ANSWERED = { ...FIRST, answer: 'I led the billing API.', input_mode: 'voice' }

  function routes(extra = {}, session = ACTIVE) {
    return respond({
      'GET /api/auth/me': [200, { user: ADA }],
      'GET /api/sessions/7': [200, { session }],
      'POST /api/sessions/7/transcribe': [200, { text: 'I led the billing API.' }],
      'POST /api/sessions/7/turns': [
        200,
        { turn: TURN, session: { ...session, transcript: [ANSWERED, NEXT] }, speech: null },
      ],
      ...extra,
    })
  }

  it('says "Mm-hm" while the reply is written, then speaks the reply', async () => {
    const spoken = fakeSpeech()
    routes()
    renderInterview()
    await userEvent.click(await screen.findByRole('button', { name: 'Record answer' }))
    await screen.findByText('What was your part?')
    // The reply waits for the filler to finish (T-109: never talk over itself).
    await spokenLast(spoken, 'What was your part?')

    const said = spoken.map((u) => u.text)
    expect(FILLERS).toContain(said[0])
    expect(said.at(-1)).toBe('What was your part?')
    expect(screen.getByText('Interviewer is speaking…')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Stop' }))
    expect(screen.queryByText('Interviewer is speaking…')).not.toBeInTheDocument()
  })

  it('speaks each panel reply, not the intro again (T-60)', async () => {
    const spoken = fakeSpeech()
    const panel = [
      { key: 'hm', name: 'Priya', title: 'the hiring manager' },
      { key: 'peer', name: 'Marcus', title: 'a senior colleague on the team' },
    ]
    const intro = { ...FIRST, segments: [{ who: 'interviewer', panelist: 'hm', text: 'Hello Ada, I am Priya.' }] }
    const planned = { ...ACTIVE, status: 'planned', mode: 'panel', panel, plan: { sections: [], reserve: [] }, transcript: [] }
    const reply = {
      action: 'next_question',
      message: 'Hi, Marcus here. Design a cache.',
      segments: [{ who: 'interviewer', panelist: 'peer', text: 'Hi, Marcus here. Design a cache.' }],
    }
    respond({
      'GET /api/auth/me': [200, { user: ADA }],
      'GET /api/sessions/7': [200, { session: planned }],
      'POST /api/sessions/7/start': [200, { session: { ...planned, status: 'active', transcript: [intro] } }],
      'POST /api/sessions/7/transcribe': [200, { text: 'I led the billing API.' }],
      // A fresh panel array every response, like the real API.
      'POST /api/sessions/7/turns': () => [
        200,
        {
          turn: reply,
          session: { ...planned, status: 'active', panel: panel.map((p) => ({ ...p })), transcript: [ANSWERED, NEXT] },
          speech: null,
        },
      ],
    })
    renderInterview()
    await userEvent.click(await screen.findByRole('button', { name: 'Start interview' }))
    await screen.findByText('Hello Ada, I am Priya.')
    spoken.at(-1).onend()
    await userEvent.click(await screen.findByRole('button', { name: 'Record answer' }))
    await screen.findByText('What was your part?')
    await spokenLast(spoken, 'Design a cache.')
    const said = spoken.map((u) => u.text)
    expect(said.filter((t) => t === 'Hello Ada, I am Priya.')).toHaveLength(1)
    expect(said.at(-1)).toBe('Design a cache.')
  })

  it('can be turned off, and stays off', async () => {
    const spoken = fakeSpeech()
    routes()
    renderInterview()
    await userEvent.click(await screen.findByLabelText('Interviewer voice'))
    await userEvent.click(screen.getByRole('button', { name: 'Record answer' }))
    await screen.findByText('What was your part?')
    expect(spoken).toEqual([])
    expect(localStorage.getItem('mi_voice')).toBe('off')

    // "Repeat" still reads the question out on request.
    await userEvent.click(screen.getByRole('button', { name: 'Repeat the question' }))
    expect(spoken.map((u) => u.text)).toEqual(['What was your part?'])
  })

  it('repeats the current question after a reload', async () => {
    const spoken = fakeSpeech()
    routes()
    renderInterview()
    await userEvent.click(await screen.findByRole('button', { name: 'Repeat the question' }))
    expect(spoken.map((u) => u.text)).toEqual(['Tell me about Acme.'])
  })

  it('says so when the browser cannot speak', async () => {
    const spoken = fakeSpeech([])
    routes()
    renderInterview()
    await userEvent.click(await screen.findByRole('button', { name: 'Repeat the question' }))
    spoken[0].onerror({ error: 'synthesis-failed' })
    expect(await screen.findByText(/couldn't play the interviewer's voice/)).toBeInTheDocument()
  })

  it('has no voice controls without speech support', async () => {
    routes()
    renderInterview()
    await screen.findByRole('button', { name: 'Record answer' })
    expect(screen.queryByLabelText('Interviewer voice')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Repeat the question' })).not.toBeInTheDocument()
  })

  it('plays Fire audio when the backend sends it', async () => {
    fakeSpeech()
    const played = []
    vi.stubGlobal('Audio', class {
      constructor(src) {
        played.push(src)
      }
      play() {
        return Promise.resolve()
      }
      pause() {}
    })
    const fire = { ...ACTIVE, voice: { provider: 'fire', persona: 'neutral' } }
    const clip = { who: 'interviewer', audio: 'data:audio/mpeg;base64,AA' }
    const calls = routes(
      {
        'POST /api/sessions/7/turns': [
          200,
          { turn: TURN, session: { ...fire, transcript: [ANSWERED, NEXT] }, speech: [clip] },
        ],
      },
      fire,
    )
    renderInterview()
    await userEvent.click(await screen.findByRole('button', { name: 'Record answer' }))
    await screen.findByText('What was your part?')
    await vi.waitFor(() => expect(played).toEqual([clip.audio]))
    const turn = calls.find((c) => c.key === 'POST /api/sessions/7/turns')
    expect(JSON.parse(turn.opts.body).speak).toBe(true)
  })

  it('asks for Fire audio where the browser cannot speak (T-148)', async () => {
    // No fakeSpeech(): jsdom has no speechSynthesis, like the Android WebView.
    const played = []
    vi.stubGlobal('Audio', class {
      constructor(src) {
        played.push(src)
      }
      play() {
        return Promise.resolve()
      }
      pause() {}
    })
    const fallback = { ...ACTIVE, voice: { provider: 'browser', persona: 'neutral', fire_fallback: true } }
    const clip = { who: 'interviewer', audio: 'data:audio/mpeg;base64,AA' }
    const calls = routes(
      {
        'POST /api/sessions/7/turns': [
          200,
          { turn: TURN, session: { ...fallback, transcript: [ANSWERED, NEXT] }, speech: [clip] },
        ],
      },
      fallback,
    )
    renderInterview()
    await userEvent.click(await screen.findByRole('button', { name: 'Record answer' }))
    await screen.findByText('What was your part?')
    await vi.waitFor(() => expect(played).toEqual([clip.audio]))
    const turn = calls.find((c) => c.key === 'POST /api/sessions/7/turns')
    expect(JSON.parse(turn.opts.body).speak).toBe(true)
  })

  it('stops asking for Fire audio once the daily voice cap is hit (T-154)', async () => {
    vi.stubGlobal('Audio', class {
      play() {
        return Promise.resolve()
      }
      pause() {}
    })
    const fallback = { ...ACTIVE, voice: { provider: 'browser', persona: 'neutral', fire_fallback: true } }
    const calls = routes(
      {
        'POST /api/sessions/7/turns': [
          200,
          { turn: TURN, session: { ...fallback, transcript: [ANSWERED, NEXT] }, speech: null, voice_capped: true },
        ],
      },
      fallback,
    )
    renderInterview()
    await userEvent.click(await screen.findByRole('button', { name: 'Record answer' }))
    expect(await screen.findByText(/used today’s spoken replies/)).toHaveTextContent('text-only until tomorrow')
    await userEvent.click(await screen.findByRole('button', { name: 'Record answer' }))
    await vi.waitFor(() => expect(calls.filter((c) => c.key === 'POST /api/sessions/7/turns')).toHaveLength(2))
    const [first, second] = calls.filter((c) => c.key === 'POST /api/sessions/7/turns')
    expect(JSON.parse(first.opts.body).speak).toBe(true)
    expect(JSON.parse(second.opts.body).speak).toBeUndefined()
  })

  it('shows and speaks the closing line', async () => {
    const spoken = fakeSpeech()
    const closing = 'That covers everything. Thank you.'
    routes({
      'POST /api/sessions/7/turns': [
        200,
        {
          turn: { action: 'wrap_up', message: closing, segments: [{ who: 'interviewer', text: closing }] },
          session: { ...ACTIVE, status: 'completed', transcript: [ANSWERED] },
        },
      ],
    })
    renderInterview()
    await userEvent.click(await screen.findByRole('button', { name: 'Record answer' }))
    expect(await screen.findByText(closing)).toBeInTheDocument()
    await spokenLast(spoken, 'Thank you.')
    expect(spoken.map((u) => u.text).slice(-2)).toEqual(['That covers everything.', 'Thank you.'])
  })
})

describe('auto-record', () => {
  const NEXT = { question_id: 2, interviewer: 'What was your part?', segments: TURN.segments, answer: null }
  function routes() {
    respond({
      'GET /api/auth/me': [200, { user: ADA }],
      'GET /api/sessions/7': [200, { session: ACTIVE }],
      'POST /api/sessions/7/transcribe': [200, { text: 'I led the billing API.' }],
      'POST /api/sessions/7/turns': [
        200,
        { turn: TURN, session: { ...ACTIVE, transcript: [{ ...FIRST, answer: 'ok' }, NEXT] } },
      ],
    })
  }

  it('starts recording when the interviewer finishes the next question', async () => {
    const spoken = fakeSpeech()
    routes()
    renderInterview()
    await userEvent.click(await screen.findByRole('button', { name: 'Record answer' }))
    await screen.findByText('What was your part?')
    await spokenLast(spoken, 'What was your part?')
    expect(screen.getByTestId('auto-record')).toHaveTextContent('0') // still speaking
    await act(async () => spoken.at(-1).onend())
    expect(screen.getByTestId('auto-record')).toHaveTextContent('1')
  })

  it('starts right away when the interviewer voice is off', async () => {
    fakeSpeech()
    localStorage.setItem('mi_voice', 'off')
    routes()
    renderInterview()
    await userEvent.click(await screen.findByRole('button', { name: 'Record answer' }))
    await screen.findByText('What was your part?')
    await vi.waitFor(() => expect(screen.getByTestId('auto-record')).toHaveTextContent('1'))
  })

  it('opens in typing mode when that was chosen', async () => {
    localStorage.setItem('mi_answer_mode', 'text')
    routes()
    renderInterview()
    expect(await screen.findByLabelText('Your answer')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Speak instead' }))
    expect(localStorage.getItem('mi_answer_mode')).toBe('voice')
  })
})

describe('your questions', () => {
  it('shows a hint when the interviewer invites questions', async () => {
    const invite = {
      question_id: 9,
      section: 'Your questions',
      interviewer: 'Before we wrap up, do you have any questions for me?',
      segments: [{ who: 'interviewer', text: 'Before we wrap up, do you have any questions for me?' }],
      answer: null,
    }
    respond({
      'GET /api/auth/me': [200, { user: ADA }],
      'GET /api/sessions/7': [200, { session: { ...ACTIVE, transcript: [{ ...FIRST, answer: 'ok' }, invite] } }],
    })
    renderInterview()
    expect(await screen.findByText('Your turn to ask.')).toBeInTheDocument()
  })
})

describe('interview controls', () => {
  // docs/INTERVIEWER_RULES.md, During the Interview (T-40).
  afterEach(() => vi.restoreAllMocks())
  it('gives one hint for the question', async () => {
    const hinted = { ...ACTIVE, transcript: [{ ...FIRST, hint: 'Think about your own part.' }] }
    const calls = respond({
      'GET /api/auth/me': [200, { user: ADA }],
      'GET /api/sessions/7': [200, { session: ACTIVE }],
      'POST /api/sessions/7/hint': [200, { hint: 'Think about your own part.', session: hinted }],
    })
    renderInterview()
    await userEvent.click(await screen.findByRole('button', { name: 'Get a hint' }))
    expect(await screen.findByText('Think about your own part.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Hint shown' })).toBeDisabled()
    expect(calls.filter((c) => c.key === 'POST /api/sessions/7/hint')).toHaveLength(1)
  })

  it('skips a question after confirming', async () => {
    const next = { question_id: 2, interviewer: 'Design a rate limiter.', segments: [{ who: 'interviewer', text: 'Design a rate limiter.' }], answer: null }
    respond({
      'GET /api/auth/me': [200, { user: ADA }],
      'GET /api/sessions/7': [200, { session: ACTIVE }],
      'POST /api/sessions/7/skip': [
        200,
        {
          turn: { action: 'next_question', message: "No problem, let's move on. Design a rate limiter.", segments: next.segments },
          session: { ...ACTIVE, transcript: [FIRST, next] },
        },
      ],
    })
    renderInterview()
    await userEvent.click(await screen.findByRole('button', { name: 'Skip question' }))
    const dialog = await screen.findByRole('alertdialog', { name: 'Skip this question?' })
    expect(dialog).toHaveTextContent('listed as unanswered')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Skip question' }))
    expect(await screen.findByText('Design a rate limiter.')).toBeInTheDocument()
  })

  it('pauses and resumes, hiding the answer controls while paused', async () => {
    const paused = { ...ACTIVE, timer: { ...ACTIVE.timer, paused: true } }
    respond({
      'GET /api/auth/me': [200, { user: ADA }],
      'GET /api/sessions/7': [200, { session: ACTIVE }],
      'POST /api/sessions/7/pause': [200, { session: paused }],
      'POST /api/sessions/7/resume': [200, { session: ACTIVE }],
    })
    renderInterview()
    await userEvent.click(await screen.findByRole('button', { name: 'Pause' }))
    expect(await screen.findByText('Interview paused')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Record answer' })).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Resume' }))
    expect(await screen.findByRole('button', { name: 'Record answer' })).toBeInTheDocument()
  })
})

describe('pressure mode', () => {
  const PRESSURED = { ...ACTIVE, pressure: { level: 3, start_level: 3, label: '60 s answers', time_limit_sec: 60 } }

  it('shows the pressure and lets you ease off or stop it', async () => {
    const calls = respond({
      'GET /api/auth/me': [200, { user: ADA }],
      'GET /api/sessions/7': [200, { session: PRESSURED }],
      'POST /api/sessions/7/pressure': (opts) => {
        const level = JSON.parse(opts.body).level
        return [200, { session: { ...PRESSURED, pressure: { ...PRESSURED.pressure, level, time_limit_sec: level >= 3 ? 60 : null } } }]
      },
    })
    renderInterview()
    expect(await screen.findByText('Pressure level 3')).toBeInTheDocument()
    expect(screen.getByText('60 s per answer')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Ease off' }))
    expect(await screen.findByText('Pressure level 2')).toBeInTheDocument()
    expect(screen.queryByText('60 s per answer')).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Stop pressure' }))
    expect(await screen.findByText('Pressure stopped')).toBeInTheDocument()
    const sent = calls.filter((c) => c.key === 'POST /api/sessions/7/pressure').map((c) => JSON.parse(c.opts.body).level)
    expect(sent).toEqual([2, 0])
  })

  it('counts down a typed answer and sends it when time is up', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    localStorage.setItem('mi_answer_mode', 'text')
    localStorage.setItem('mi_voice', 'off')
    const calls = respond({
      'GET /api/auth/me': [200, { user: ADA }],
      'GET /api/sessions/7': [200, { session: PRESSURED }],
      'POST /api/sessions/7/turns': [200, { turn: TURN, session: { ...PRESSURED, transcript: [{ ...FIRST, answer: 'Partial answer' }] } }],
    })
    renderInterview()
    const box = await screen.findByLabelText('Your answer')
    expect(screen.getByRole('timer')).toHaveTextContent('60 s left')
    await act(async () => {
      box.focus()
    })
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
    await user.type(box, 'Partial answer')
    await act(async () => vi.advanceTimersByTime(61_000))
    await vi.waitFor(() => expect(calls.some((c) => c.key === 'POST /api/sessions/7/turns')).toBe(true))
    vi.useRealTimers()
  })

  // T-109: time ran out → a polite interruption, said once, and the answer goes in.
  const LINE = "Sorry, I'm going to have to stop you there; we're out of time for this one."
  const TIMED = { ...PRESSURED, interruptions: [LINE] }
  const AFTER = {
    action: 'next_question',
    message: `${LINE} Next: tell me about a failure.`,
    segments: [
      { who: 'interviewer', text: LINE, interruption: true },
      { who: 'interviewer', text: 'Next: tell me about a failure.' },
    ],
  }
  const NEXT_Q = { question_id: 2, interviewer: AFTER.message, segments: AFTER.segments, answer: null }

  it('sends what was typed, even nothing, marked with the interruption', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    localStorage.setItem('mi_answer_mode', 'text')
    localStorage.setItem('mi_voice', 'off')
    const calls = respond({
      'GET /api/auth/me': [200, { user: ADA }],
      'GET /api/sessions/7': [200, { session: TIMED }],
      'POST /api/sessions/7/turns': [
        200,
        { turn: AFTER, session: { ...TIMED, transcript: [{ ...FIRST, answer: '(Time ran out before I answered.)', cut_off: true }, NEXT_Q] } },
      ],
    })
    renderInterview()
    const box = await screen.findByLabelText('Your answer')
    await act(async () => {
      box.focus()
    })
    await act(async () => vi.advanceTimersByTime(61_000))
    await vi.waitFor(() => expect(calls.some((c) => c.key === 'POST /api/sessions/7/turns')).toBe(true))
    const body = JSON.parse(calls.find((c) => c.key === 'POST /api/sessions/7/turns').opts.body)
    expect(body.interruption).toBe(LINE)
    expect(body.text).toBe('')
    expect(await screen.findByText(/cut off by time limit/)).toBeInTheDocument()
    vi.useRealTimers()
  })

  it('says the interruption at once and does not say it again with the reply', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    localStorage.setItem('mi_answer_mode', 'text')
    const spoken = fakeSpeech()
    respond({
      'GET /api/auth/me': [200, { user: ADA }],
      'GET /api/sessions/7': [200, { session: TIMED }],
      'POST /api/sessions/7/turns': [200, { turn: AFTER, session: { ...TIMED, transcript: [{ ...FIRST, answer: 'Partial', cut_off: true }, NEXT_Q] } }],
    })
    renderInterview()
    const box = await screen.findByLabelText('Your answer')
    // The first question was spoken; let it end so the answer clock runs.
    await act(async () => spoken.at(-1)?.onend?.())
    await act(async () => {
      box.focus()
    })
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
    await user.type(box, 'Partial')
    await act(async () => vi.advanceTimersByTime(61_000))
    await vi.waitFor(() => expect(spoken.some((u) => u.text === "Sorry, I'm going to have to stop you there; we're out of time for this one.")).toBe(true))
    await act(async () => vi.advanceTimersByTime(9_000))
    await vi.waitFor(() => expect(spoken.at(-1)?.text).toBe('Next: tell me about a failure.'))
    const said = spoken.map((u) => u.text)
    expect(said.filter((t) => t.startsWith("Sorry, I'm going to have to stop you there"))).toHaveLength(1)
    vi.useRealTimers()
  })
})
