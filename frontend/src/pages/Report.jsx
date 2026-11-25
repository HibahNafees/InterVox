import { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import CommentList from '../components/CommentList'
import { useDialogs } from '../components/ConfirmDialog'
import PublicShell from '../components/PublicShell'
import Recorder from '../components/Recorder'
import WorkView from '../components/WorkView'
import { NoRecordingsNotice } from './Debrief'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { hasOrgs } from '../lib/orgs'
import { canRecord, MAX_ANSWER_MS } from '../lib/recording'
import { describeScene } from '../lib/whiteboard'

// Try again on a coding or design question brings back the editor or whiteboard.
const CodePad = lazy(() => import('../components/CodePad'))
const Whiteboard = lazy(() => import('../components/Whiteboard'))
const TOOLS = { coding: 'code', system_design: 'whiteboard' }

const POLL_MS = 2500
const VERDICT = {
  hire: ['Hire', 'bg-green-100 text-green-800'],
  'lean hire': ['Lean hire', 'bg-amber-100 text-amber-800'],
  'no hire': ['No hire', 'bg-red-100 text-red-800'],
}
// A negotiation is judged as a negotiation, not as hire / no hire.
const NEGOTIATION_VERDICT = {
  hire: ['Strong negotiation', 'bg-green-100 text-green-800'],
  'lean hire': ['Solid, room to push', 'bg-amber-100 text-amber-800'],
  'no hire': ['Needs more practice', 'bg-red-100 text-red-800'],
}
const CHANGE = {
  added: 'bg-green-100 text-green-800',
  cut: 'bg-red-100 text-red-800',
  reframed: 'bg-navy-100 text-navy-800',
}
const EXT = { 'audio/webm': 'webm', 'audio/ogg': 'ogg', 'audio/mp4': 'm4a' }

function fmtScore(s) {
  return s == null ? '–' : s.toFixed(1)
}

function fmtTime(sec) {
  if (sec == null) return '–'
  return `${Math.floor(sec / 60)}:${String(Math.round(sec % 60)).padStart(2, '0')}`
}

function scoreColor(s) {
  if (s == null) return 'bg-slate-100 text-slate-500'
  if (s >= 4) return 'bg-emerald-100 text-emerald-800'
  if (s >= 3) return 'bg-amber-100 text-amber-800'
  return 'bg-rose-100 text-rose-800'
}

function barColor(s) {
  if (s >= 4) return 'from-emerald-400 to-navy-500'
  if (s >= 3) return 'from-amber-300 to-orange-400'
  return 'from-rose-400 to-red-500'
}

// The overall score as a ring that fills to score/5.
function ScoreRing({ value }) {
  const pct = value == null ? 0 : (value / 5) * 100
  return (
    <div
      role="img"
      aria-label={`Overall ${fmtScore(value)} out of 5`}
      className="grid h-28 w-28 shrink-0 place-items-center rounded-full"
      style={{ background: `conic-gradient(#8b5cf6, #d946ef ${pct}%, var(--color-ring-track) ${pct}%)` }}
    >
      <div className="grid h-[5.5rem] w-[5.5rem] place-items-center rounded-full bg-surface">
        <p className="text-center">
          <span className="block text-3xl font-extrabold tabular-nums text-slate-900">{fmtScore(value)}</span>
          <span className="text-xs font-medium text-slate-500">out of 5</span>
        </p>
      </div>
    </div>
  )
}

function Score({ value, label = 'Score' }) {
  return (
    <span
      aria-label={`${label} ${fmtScore(value)} out of 5`}
      className={`inline-block rounded-full px-2.5 py-0.5 font-bold tabular-nums ${scoreColor(value)}`}
    >
      {fmtScore(value)}
      <span className="text-xs font-normal"> / 5</span>
    </span>
  )
}

// Wraps each weak-moment quote found in `text` in a <mark> with the reason as a tooltip.
function Highlighted({ text, moments = [] }) {
  const lower = text.toLowerCase()
  const spans = []
  for (const m of moments) {
    const at = lower.indexOf(m.quote.toLowerCase())
    if (at >= 0 && !spans.some((s) => at < s.end && at + m.quote.length > s.start)) {
      spans.push({ start: at, end: at + m.quote.length, why: m.why })
    }
  }
  spans.sort((a, b) => a.start - b.start)
  const parts = []
  let pos = 0
  for (const s of spans) {
    if (s.start > pos) parts.push(text.slice(pos, s.start))
    parts.push(
      <mark key={s.start} title={s.why} className="rounded bg-amber-200/70 px-0.5 text-amber-900">
        {text.slice(s.start, s.end)}
      </mark>,
    )
    pos = s.end
  }
  parts.push(text.slice(pos))
  return <>{parts}</>
}

function Delivery({ d }) {
  if (!d) return null
  const fillers = Object.entries(d.fillers || {})
  return (
    <div className="text-sm">
      <dl className="flex flex-wrap gap-x-6 gap-y-1 text-slate-700">
        <div>
          <dt className="inline text-slate-500">Time </dt>
          <dd className="inline tabular-nums">
            {fmtTime(d.duration_sec)}
            {d.budget_sec ? ` of ${fmtTime(d.budget_sec)}` : ''}
          </dd>
        </div>
        <div>
          <dt className="inline text-slate-500">Words </dt>
          <dd className="inline tabular-nums">{d.words}</dd>
        </div>
        {d.wpm != null && (
          <div>
            <dt className="inline text-slate-500">Pace </dt>
            <dd className="inline tabular-nums">{d.wpm} wpm</dd>
          </div>
        )}
        {d.spoken && (
          <div>
            <dt className="inline text-slate-500">Fillers </dt>
            <dd className="inline">
              {fillers.length ? fillers.map(([k, v]) => `${k} ×${v}`).join(', ') : 'none'}
            </dd>
          </div>
        )}
      </dl>
      {d.tips?.length > 0 && (
        <ul className="mt-2 list-disc space-y-1 pl-5 text-slate-700">
          {d.tips.map((t) => (
            <li key={t}>{t}</li>
          ))}
        </ul>
      )}
    </div>
  )
}

function Star({ star }) {
  if (!star) return null
  return (
    <div>
      <h4 className="text-sm font-medium">STAR structure</h4>
      <ul className="mt-1 flex flex-wrap gap-2 text-xs">
        {['situation', 'task', 'action', 'result'].map((k) => (
          <li
            key={k}
            className={`rounded-full px-2.5 py-0.5 font-medium capitalize ${star[k] ? 'bg-emerald-100 text-emerald-800' : 'bg-slate-100 text-slate-500 line-through'}`}
          >
            {k}
          </li>
        ))}
      </ul>
      {star.note && <p className="mt-1 text-sm text-slate-600">{star.note}</p>}
    </div>
  )
}

const CONFIDENCE = {
  high: ['High confidence', 'bg-emerald-50 text-emerald-700 ring-emerald-200'],
  medium: ['Medium confidence', 'bg-accent-50 text-accent-700 ring-accent-200'],
  low: ['Low confidence', 'bg-brand-50 text-brand-700 ring-brand-200'],
}

function Evaluation({ e, said, roleplay }) {
  const [confLabel, confTone] = CONFIDENCE[e.confidence] ?? []
  return (
    <div className="space-y-5">
      {e.summary && (
        <div className="space-y-2">
          <p className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
            <span className="chip bg-slate-100 text-slate-600">AI coach's judgment</span>
            {confLabel && <span className={`chip ring-1 ${confTone}`}>{confLabel}</span>}
            {e.confidence !== 'high' && e.confidence_note && <span>{e.confidence_note}</span>}
          </p>
          <p className="text-slate-700">{e.summary}</p>
        </div>
      )}

      {e.strengths?.length > 0 && (
        <div className="rounded-2xl bg-emerald-50/70 p-4 ring-1 ring-emerald-200">
          <h4 className="text-sm font-semibold text-emerald-800">What you did well</h4>
          <ul className="mt-1 space-y-1 text-sm text-emerald-900">
            {e.strengths.map((t) => (
              <li key={t} className="flex gap-2">
                <span aria-hidden="true">✓</span>
                {t}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="grid gap-4 md:grid-cols-2">
        <div className="rounded-2xl bg-slate-50 p-4 ring-1 ring-slate-200">
          <h4 className="mb-2 text-xs font-semibold tracking-wide text-slate-500 uppercase">
            What you said
          </h4>
          {said.map((s, i) => (
            <div key={i} className="mb-2 last:mb-0">
              {s.is_follow_up && (
                <p className="text-xs italic text-slate-500">
                  {roleplay ? 'They said' : 'Follow-up'}: {s.interviewer}
                </p>
              )}
              <p className="whitespace-pre-wrap">
                <Highlighted text={s.answer} moments={e.weak_moments} />
              </p>
              <WorkView work={s.work} />
            </div>
          ))}
        </div>
        <div className="rounded-2xl bg-gradient-to-br from-brand-50 to-accent-50 p-4 ring-1 ring-brand-200">
          <h4 className="mb-2 text-xs font-semibold tracking-wide text-brand-700 uppercase">
            <span aria-hidden="true">✨ </span>A stronger version
          </h4>
          <p className="whitespace-pre-wrap">{e.stronger_version}</p>
          <p className="mt-2 text-xs text-brand-700">
            Built only from your résumé and answers. Fill in the [bracketed] parts with your
            real details.
          </p>
        </div>
      </div>

      {e.weak_moments.length > 0 && (
        <div>
          <h4 className="text-sm font-medium">Weak moments</h4>
          <ul className="mt-1 space-y-1 text-sm">
            {e.weak_moments.map((w) => (
              <li key={w.quote}>
                <mark className="rounded bg-amber-200/70 px-0.5 text-amber-900">“{w.quote}”</mark>{' '}
                <span className="text-slate-600">— {w.why}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {e.changes.length > 0 && (
        <div>
          <h4 className="text-sm font-medium">What changed and why</h4>
          <ul className="mt-1 space-y-1 text-sm">
            {e.changes.map((c, i) => (
              <li key={i}>
                <span className={`mr-2 rounded px-1.5 py-0.5 text-xs capitalize ${CHANGE[c.kind]}`}>
                  {c.kind}
                </span>
                {c.text}
                {c.reason && <span className="text-slate-600"> — {c.reason}</span>}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="grid gap-4 md:grid-cols-2">
        {e.missing_points.length > 0 && (
          <div>
            <h4 className="text-sm font-medium">What a strong answer covers</h4>
            <ul className="mt-1 space-y-1 text-sm">
              {e.missing_points.map((m) => (
                <li key={m.point} className="flex gap-2">
                  <span aria-label={m.covered ? 'Covered' : 'Missing'} className={m.covered ? 'text-green-700' : 'text-red-600'}>
                    {m.covered ? '✓' : '✗'}
                  </span>
                  <span className={m.covered ? 'text-slate-600' : ''}>{m.point}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
        <div>
          <h4 className="text-sm font-medium">Rubric</h4>
          <ul className="mt-2 space-y-2.5 text-sm">
            {e.criteria.map((c) => (
              <li key={c.name}>
                <div className="flex items-baseline justify-between gap-2">
                  <span className="font-medium text-slate-800">{c.name}</span>
                  <span className="font-semibold tabular-nums">{c.score}/5</span>
                </div>
                <div aria-hidden="true" className="mt-1 h-1.5 overflow-hidden rounded-full bg-slate-100">
                  <div
                    className={`h-full rounded-full bg-gradient-to-r ${barColor(c.score)}`}
                    style={{ width: `${(c.score / 5) * 100}%` }}
                  />
                </div>
                {c.comment && <p className="mt-1 text-slate-600">{c.comment}</p>}
              </li>
            ))}
          </ul>
        </div>
      </div>

      <Star star={e.star} />
      {e.tips.length > 0 && (
        <div>
          <h4 className="text-sm font-medium">Tips for this question</h4>
          <ul className="mt-1 list-disc space-y-1 pl-5 text-sm text-slate-700">
            {e.tips.map((t) => (
              <li key={t}>{t}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

function TryAgain({ sessionId, question, beforeScore, onAttempt }) {
  const [open, setOpen] = useState(false)
  const [mode, setMode] = useState(() => (canRecord() ? 'voice' : 'text'))
  const [text, setText] = useState('')
  const [phase, setPhase] = useState('idle') // idle | transcribing | scoring
  const [error, setError] = useState('')
  const [started, setStarted] = useState(0)
  const busy = phase !== 'idle'
  const tool = TOOLS[question.module] ?? null
  // Start from the code they wrote the first time.
  const firstCode = question.exchange.find((s) => s.work?.kind === 'code')?.work
  const [code, setCode] = useState(() => ({
    language: firstCode?.language ?? 'python',
    content: firstCode?.content ?? '',
  }))
  const board = useRef([])

  function currentWork() {
    if (tool === 'code' && code.content.trim()) return { kind: 'code', language: code.language, content: code.content }
    if (tool === 'whiteboard') {
      const content = describeScene(board.current)
      if (content) return { kind: 'whiteboard', content }
    }
    return null
  }

  async function send(answer, meta) {
    setPhase('scoring')
    const work = currentWork()
    try {
      const data = await api(`/sessions/${sessionId}/questions/${question.question_id}/retry`, {
        method: 'POST',
        body: {
          text: answer.trim() || (work?.kind === 'code' ? '(My answer is in the code editor.)' : '(My answer is on the whiteboard.)'),
          ...meta,
          ...(work ? { work } : {}),
        },
      })
      setText('')
      onAttempt(question.question_id, data.attempt)
    } catch (err) {
      setError(err.message)
      setText(answer)
      if (meta.input_mode === 'voice') setMode('text')
    } finally {
      setPhase('idle')
    }
  }

  async function onRecorded(blob, durationMs) {
    setError('')
    setPhase('transcribing')
    const form = new FormData()
    form.append('audio', blob, `answer.${EXT[blob.type.split(';')[0]] ?? 'webm'}`)
    let transcript
    try {
      transcript = (await api(`/sessions/${sessionId}/transcribe`, { method: 'POST', body: form })).text
    } catch (err) {
      setError(err.message)
      setPhase('idle')
      return
    }
    await send(transcript, { duration_ms: Math.min(durationMs, MAX_ANSWER_MS), input_mode: 'voice' })
  }

  function sendTyped(e) {
    e.preventDefault()
    if ((!text.trim() && !currentWork()) || busy) return
    setError('')
    send(text, { duration_ms: Math.min(Date.now() - started, MAX_ANSWER_MS), input_mode: 'text' })
  }

  const last = question.attempts.at(-1)
  return (
    <div className="space-y-3 print:hidden">
      {question.attempts.length > 0 && (
        <div className="rounded-2xl bg-navy-50/70 p-4 text-sm ring-1 ring-navy-200">
          <p className="font-semibold">
            Try again: <Score value={beforeScore} label="Before" /> →{' '}
            <Score value={last.evaluation?.score} label="After" />
            <span className="ml-2 font-normal text-slate-500">
              (attempt {last.attempt_no})
            </span>
          </p>
          <p className="mt-2 whitespace-pre-wrap text-slate-700">{last.answer}</p>
          <WorkView work={last.work} />
          {last.evaluation && (
            <details className="mt-2">
              <summary className="cursor-pointer font-medium text-brand-700">Feedback on this attempt</summary>
              <div className="mt-3">
                <Evaluation e={last.evaluation} said={[{ answer: last.answer }]} />
              </div>
            </details>
          )}
        </div>
      )}
      {!open ? (
        <button
          type="button"
          onClick={() => {
            setOpen(true)
            setStarted(Date.now())
          }}
          className="btn-secondary"
        >
          <span aria-hidden="true">↻</span>Try again
        </button>
      ) : (
        <div className="space-y-3 rounded-2xl border border-brand-100 bg-brand-50/40 p-4">
          <p className="text-sm text-slate-600">Answer “{question.text}” again.</p>
          {tool && (
            <Suspense fallback={<p className="text-sm text-slate-500">Loading…</p>}>
              {tool === 'code' ? (
                <CodePad code={code} onChange={setCode} />
              ) : (
                <Whiteboard onChange={(elements) => (board.current = elements)} />
              )}
            </Suspense>
          )}
          {mode === 'voice' ? (
            <Recorder onRecorded={onRecorded} disabled={busy} />
          ) : (
            <form onSubmit={sendTyped} className="space-y-2">
              <textarea
                aria-label="Your new answer"
                rows={4}
                value={text}
                disabled={busy}
                onChange={(e) => setText(e.target.value)}
                className="field"
              />
              <button
                type="submit"
                disabled={busy || (!text.trim() && !tool)}
                className="btn-primary text-sm"
              >
                Score my new answer
              </button>
            </form>
          )}
          {busy && (
            <p role="status" className="animate-pulse text-sm text-slate-500">
              {phase === 'transcribing' ? 'Listening back to your answer…' : 'Scoring your answer…'}
            </p>
          )}
          {error && (
            <p role="alert" className="text-sm text-red-600">
              {error}
            </p>
          )}
          <div className="flex gap-4 text-sm">
            {canRecord() && (
              <button
                type="button"
                disabled={busy}
                onClick={() => setMode((m) => (m === 'voice' ? 'text' : 'voice'))}
                className="btn-link"
              >
                {mode === 'voice' ? 'Type instead' : 'Speak instead'}
              </button>
            )}
            <button
              type="button"
              disabled={busy}
              onClick={() => setOpen(false)}
              className="btn-link"
            >
              Close
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

function QuestionCard({ q, index, sessionId, onAttempt, failed, shared }) {
  const e = q.evaluation
  return (
    <article className="card space-y-5 p-6 break-inside-avoid">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="eyebrow">
            Question {index + 1} · {q.section}
            {q.is_bonus ? ' · bonus' : ''}
          </p>
          <h3 className="mt-1 text-lg font-semibold text-slate-900">{q.text}</h3>
          {q.scenario && (
            <p className="mt-1 text-sm text-amber-900">
              Role-play with {q.scenario.character}. Your goal: {q.scenario.goal}
            </p>
          )}
          {q.exchange.some((x) => x.cut_off) && (
            <p className="mt-2 chip bg-amber-100 text-amber-900">
              ⏱ Cut off by the time limit: scored on what you said before time ran out
            </p>
          )}
        </div>
        {e ? (
          <Score value={e.score} />
        ) : failed || q.set_aside ? (
          <span className="chip bg-brand-100 text-brand-700">Couldn't be scored</span>
        ) : (
          <span className="text-sm text-slate-500">Scoring…</span>
        )}
      </header>
      <Delivery d={q.delivery} />
      {e ? (
        <Evaluation e={e} said={q.exchange} roleplay={Boolean(q.scenario)} />
      ) : (
        <div className="space-y-2">
          {q.set_aside && (
            <p className="text-sm text-slate-500">
              The AI couldn't score this answer, so the overall score and summary leave it out.
            </p>
          )}
          {q.exchange.map((s, i) => (
            <div key={i}>
              <p className="whitespace-pre-wrap text-slate-700">{s.answer}</p>
              <WorkView work={s.work} />
            </div>
          ))}
        </div>
      )}
      {e && !shared && <TryAgain sessionId={sessionId} question={q} beforeScore={e.score} onAttempt={onAttempt} />}
    </article>
  )
}

function ThankYou({ sessionId }) {
  const [email, setEmail] = useState(null)
  const [body, setBody] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [copied, setCopied] = useState(false)

  async function draft() {
    setError('')
    setBusy(true)
    try {
      const { email: e } = await api(`/sessions/${sessionId}/thank-you`, { method: 'POST' })
      setEmail(e)
      setBody(e.body)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  async function copy() {
    const text = `Subject: ${email.subject}\n\n${body}`
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
    } catch {
      window.prompt('Copy your email', text)
    }
  }

  if (!email) {
    return (
      <div className="flex flex-wrap items-center gap-3 print:hidden">
        <button type="button" onClick={draft} disabled={busy} className="btn-secondary">
          <span aria-hidden="true">✉️</span>
          {busy ? 'Drafting…' : 'Thank-you email'}
        </button>
        <span className="text-xs text-slate-500">A short draft to send after a real interview.</span>
        {error && (
          <p role="alert" className="basis-full text-sm text-red-600">
            {error}
          </p>
        )}
      </div>
    )
  }
  return (
    <div className="card space-y-3 p-6 print:hidden">
      <h2 className="text-lg font-bold">Thank-you email</h2>
      <p className="text-sm">
        <span className="font-semibold">Subject:</span> {email.subject}
      </p>
      <textarea
        aria-label="Email body"
        rows={9}
        value={body}
        onChange={(e) => setBody(e.target.value)}
        className="field text-sm"
      />
      <p className="text-xs text-slate-500">Fill in anything in [brackets] before sending.</p>
      <button type="button" onClick={copy} className="btn-primary text-sm">
        {copied ? 'Copied' : 'Copy email'}
      </button>
    </div>
  )
}

// After a debrief: it's kept until deleted; its job posting can be saved or deleted.
function DebriefKeep({ debrief }) {
  const navigate = useNavigate()
  const [jd, setJd] = useState(debrief.jd)
  const { confirm, notify } = useDialogs()
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function act(call) {
    setError('')
    setBusy(true)
    try {
      await call()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  async function removeDebrief() {
    const deleted = await confirm({
      title: 'Delete this debrief?',
      message: 'This debrief and its report will be permanently deleted. This can’t be undone.',
      confirmLabel: 'Delete',
      busyLabel: 'Deleting…',
      danger: true,
      onConfirm: () => api(`/debriefs/${debrief.id}`, { method: 'DELETE' }),
    })
    if (!deleted) return
    notify('Debrief deleted')
    navigate('/debrief')
  }
  const saveJd = () =>
    act(async () => {
      await api(`/documents/${jd.id}/save`, { method: 'POST' })
      setJd({ ...jd, saved: true })
    })
  async function removeJd() {
    const deleted = await confirm({
      title: 'Delete this job posting?',
      message: `“${jd.title}” will be permanently deleted. This debrief stays.`,
      confirmLabel: 'Delete',
      busyLabel: 'Deleting…',
      danger: true,
      onConfirm: () => api(`/documents/${jd.id}`, { method: 'DELETE' }),
    })
    if (!deleted) return
    setJd(null)
    notify('Job posting deleted')
  }

  return (
    <div className="card space-y-3 p-6">
      <p className="eyebrow">Keep or delete</p>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-slate-600">This debrief is saved under Past debriefs until you delete it.</p>
        <button type="button" onClick={removeDebrief} disabled={busy} className="btn-secondary hover:text-red-600">
          Delete debrief
        </button>
      </div>
      {jd && (
        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line-soft pt-3">
          <p className="text-sm text-slate-600">
            Job posting <span className="font-medium text-ink">{jd.title}</span>
            {jd.saved ? ': saved until you delete it.' : ': auto-deletes after 30 days unless you save it.'}
          </p>
          <span className="flex gap-2">
            {!jd.saved && (
              <button type="button" onClick={saveJd} disabled={busy} className="btn-secondary">
                Save job posting
              </button>
            )}
            <button type="button" onClick={removeJd} disabled={busy} className="btn-secondary hover:text-red-600">
              Delete job posting
            </button>
          </span>
        </div>
      )}
      {error && (
        <p role="alert" className="text-sm text-red-600">
          {error}
        </p>
      )}
    </div>
  )
}

function NextRound({ debrief }) {
  const navigate = useNavigate()
  const [next, setNext] = useState(debrief.next_round)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function run(action) {
    setError('')
    setBusy(true)
    try {
      if (action === 'predict') {
        setNext((await api(`/debriefs/${debrief.id}/predict`, { method: 'POST' })).debrief.next_round)
      } else {
        const { session } = await api(`/debriefs/${debrief.id}/practice`, { method: 'POST', body: { duration_min: 10 } })
        navigate(`/interview/${session.id}`)
      }
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="card space-y-4 p-6">
      <div>
        <p className="eyebrow">Next round</p>
        <h2 className="text-lg font-bold">Questions the next round will likely ask</h2>
        <p className="text-sm text-slate-500">A prediction from this interview, not a promise.</p>
      </div>
      {next.length ? (
        <ol className="space-y-2">
          {next.map((q, i) => (
            <li key={q.question} className="flex gap-3 text-sm">
              <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-night text-xs font-bold text-white">
                {i + 1}
              </span>
              <span>
                <span className="font-medium text-ink">{q.question}</span>
                {q.why && <span className="block text-slate-500">{q.why}</span>}
              </span>
            </li>
          ))}
        </ol>
      ) : (
        <p className="text-sm text-slate-500">The prediction isn't ready yet.</p>
      )}
      {next.length ? (
        <button type="button" onClick={() => run('practice')} disabled={busy} className="btn-primary">
          {busy ? 'Building your practice…' : 'Practice the next round'}
        </button>
      ) : (
        <button type="button" onClick={() => run('predict')} disabled={busy} className="btn-secondary">
          {busy ? 'Predicting…' : 'Predict the next round'}
        </button>
      )}
      {error && (
        <p role="alert" className="text-sm text-red-600">
          {error}
        </p>
      )}
    </div>
  )
}

// Opt-in camera feedback, measured in the browser; never part of the score.
function BodyLanguageCard({ b }) {
  const rows = [
    ['Eye contact', b.eye_contact_pct, 'of the time looking at the camera'],
    ['Posture', b.upright_pct, 'of the time sitting upright'],
    ['Fidgeting', b.fidget_pct, 'of the time moving a lot', true],
  ].filter(([, v]) => v != null)
  return (
    <div className="card space-y-3 p-6">
      <div>
        <p className="eyebrow">
          <span aria-hidden="true">📷 </span>Body language
        </p>
        <p className="text-sm text-slate-600">
          From your camera on {b.answers} answer{b.answers === 1 ? '' : 's'}, measured on your device. A rough
          guide (lighting and camera angle affect it), and not part of your score.
        </p>
      </div>
      <ul className="grid gap-3 sm:grid-cols-3">
        {rows.map(([label, value, what, lowIsGood]) => {
          const good = lowIsGood ? value <= 25 : value >= 60
          return (
            <li key={label} className="rounded-2xl bg-slate-50 p-4 ring-1 ring-slate-200">
              <p className="text-sm font-semibold text-ink">{label}</p>
              <p className={`text-2xl font-extrabold ${good ? 'text-emerald-700' : 'text-brand-700'}`}>{value}%</p>
              <p className="text-xs text-slate-500">{what}</p>
            </li>
          )
        })}
      </ul>
      {b.tips.length > 0 && (
        <ul className="list-disc space-y-1 pl-5 text-sm text-slate-700">
          {b.tips.map((t) => (
            <li key={t}>{t}</li>
          ))}
        </ul>
      )}
    </div>
  )
}

function Summary({ report }) {
  const a = report.analytics
  const verdicts = report.mode === 'negotiation' ? NEGOTIATION_VERDICT : VERDICT
  const [label, color] = verdicts[report.verdict] ?? ['–', 'bg-slate-100 text-slate-600']
  const fillers = Object.entries(a?.fillers ?? {})
  return (
    <div className="space-y-4">
      <div className="card flex flex-wrap items-center gap-6 p-6">
        <ScoreRing value={report.overall_score} />
        <div className="min-w-0 flex-1 basis-60 space-y-2">
          <p className="eyebrow">Overall</p>
          <span className={`inline-block rounded-full px-3 py-1 text-sm font-bold ${color}`}>{label}</span>
          {report.verdict_reason && <p className="text-slate-700">{report.verdict_reason}</p>}
        </div>
      </div>

      {report.takeaways.length > 0 && (
        <div className="rounded-2xl bg-gradient-to-br from-brand-600 via-accent-600 to-accent-500 p-6 text-white shadow-lg shadow-accent-500/20">
          <h2 className="text-lg font-bold">Top 3 takeaways</h2>
          <ol className="mt-3 space-y-2">
            {report.takeaways.map((t, i) => (
              <li key={t} className="flex gap-3">
                <span aria-hidden="true" className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-white/20 text-sm font-bold">
                  {i + 1}
                </span>
                <span className="text-white/95">{t}</span>
              </li>
            ))}
          </ol>
        </div>
      )}

      {report.pressure && (
        <div className="card flex flex-wrap items-center gap-5 p-6">
          <span aria-hidden="true" className="grid h-14 w-14 place-items-center rounded-2xl bg-gradient-to-br from-brand-100 to-accent-200 text-2xl">
            🔥
          </span>
          <div className="min-w-0 flex-1">
            <p className="eyebrow">Pressure interview</p>
            <h2 className="text-lg font-bold">
              Composure:{' '}
              {report.pressure.composure?.pct != null ? `${report.pressure.composure.pct}%` : 'not yet'}
            </h2>
            <p className="text-sm text-slate-600">{report.pressure.composure?.label}</p>
            <p className="mt-1 text-xs text-slate-500">
              Started at level {report.pressure.start_level}
              {report.pressure.level !== report.pressure.start_level &&
                `, eased to ${report.pressure.level ? `level ${report.pressure.level}` : 'off'}`}
              {report.pressure.composure?.baseline != null &&
                ` · compared with your normal ${report.pressure.composure.same_job ? 'interviews for this job' : 'interviews'} (${report.pressure.composure.baseline.toFixed(1)} / 5)`}
              . Scores use the same standards with or without pressure.
            </p>
          </div>
        </div>
      )}

      {report.body_language && <BodyLanguageCard b={report.body_language} />}

      {report.their_questions && (
        <div className="card p-6">
          <h2 className="text-lg font-bold">Your questions for them</h2>
          {report.their_questions.summary && <p className="text-sm text-slate-600">{report.their_questions.summary}</p>}
          <ul className="mt-3 space-y-3 text-sm">
            {report.their_questions.questions.map((q) => (
              <li key={q.asked} className="flex gap-3">
                <span className={`chip h-fit shrink-0 tabular-nums ${scoreColor(q.score)}`}>{q.score}/5</span>
                <span>
                  <span className="font-medium text-ink">“{q.asked}”</span>
                  <span className="block text-slate-600">{q.comment}</span>
                  {q.better && (
                    <span className="block text-slate-600">
                      <span className="font-semibold text-emerald-700">Sharper:</span> {q.better}
                    </span>
                  )}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {report.competencies?.length > 0 && (
        <div className="card p-6">
          <h2 className="text-lg font-bold">Competencies</h2>
          <p className="text-sm text-slate-500">Each rubric criterion averaged over the questions that tested it</p>
          <ul className="mt-4 grid gap-x-8 gap-y-3 sm:grid-cols-2">
            {report.competencies.map((c) => (
              <li key={c.name}>
                <div className="flex items-baseline justify-between gap-2 text-sm">
                  <span className="font-medium text-slate-800">{c.name}</span>
                  <span className="font-semibold tabular-nums">{c.score.toFixed(1)}/5</span>
                </div>
                <div aria-hidden="true" className="mt-1 h-2 overflow-hidden rounded-full bg-slate-100">
                  <div
                    className={`h-full rounded-full bg-gradient-to-r ${barColor(c.score)}`}
                    style={{ width: `${(c.score / 5) * 100}%` }}
                  />
                </div>
                <p className="mt-0.5 text-xs text-slate-500">
                  {c.questions} question{c.questions === 1 ? '' : 's'}
                </p>
              </li>
            ))}
          </ul>
        </div>
      )}

      {report.exercises?.length > 0 && (
        <div className="card p-6">
          <h2 className="text-lg font-bold">Recommended exercises</h2>
          <ol className="mt-3 space-y-2">
            {report.exercises.map((x, i) => (
              <li key={x} className="flex gap-3">
                <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-accent-100 text-sm font-bold text-accent-700">
                  {i + 1}
                </span>
                <span className="text-slate-700">{x}</span>
              </li>
            ))}
          </ol>
        </div>
      )}

      {a && (
        <div className="card p-6">
          <h2 className="font-bold text-slate-900">Delivery</h2>
          <dl className="mt-2 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
            <div>
              <dt className="text-slate-500">Answer time</dt>
              <dd className="tabular-nums">
                {fmtTime(a.answer_sec)} of {fmtTime(a.budget_sec)} planned
              </dd>
            </div>
            <div>
              <dt className="text-slate-500">Average pace</dt>
              <dd className="tabular-nums">{a.avg_wpm != null ? `${a.avg_wpm} wpm` : 'Spoken answers only'}</dd>
            </div>
            <div>
              <dt className="text-slate-500">Filler words</dt>
              <dd>{fillers.length ? fillers.map(([k, v]) => `${k} ×${v}`).join(', ') : 'none'}</dd>
            </div>
            <div>
              <dt className="text-slate-500">Over time</dt>
              <dd className="tabular-nums">
                {a.over_budget} of {a.questions} answers
              </dd>
            </div>
          </dl>
        </div>
      )}
    </div>
  )
}

// A read-only link for a mentor or friend; turning it off makes the old link stop working.
function ShareReport({ sessionId, token: initial }) {
  const [token, setToken] = useState(initial || null)
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState('')
  const link = token ? `${window.location.origin}/shared/${token}` : ''

  async function run(method) {
    setBusy(true)
    setNote('')
    try {
      const data = await api(`/sessions/${sessionId}/report/share`, { method })
      setToken(method === 'POST' ? data.share_token : null)
      setNote(method === 'POST' ? 'Anyone with this link can read the report.' : 'The link is turned off.')
    } catch (err) {
      setNote(err.message)
    } finally {
      setBusy(false)
    }
  }

  async function copy() {
    try {
      await navigator.clipboard.writeText(link)
      setNote('Link copied.')
    } catch {
      window.prompt('Copy this link', link)
    }
  }

  return (
    <div className="card space-y-2 p-4 text-sm print:hidden">
      <div className="flex flex-wrap items-center gap-3">
        <span className="font-semibold text-slate-800">Share this report</span>
        {token ? (
          <>
            <input
              readOnly
              value={link}
              aria-label="Share link"
              onFocus={(e) => e.target.select()}
              className="min-w-0 flex-1 rounded-lg border border-slate-200 bg-surface px-2 py-1 text-slate-600"
            />
            <button type="button" onClick={copy} className="btn-secondary px-3 py-1">
              Copy link
            </button>
            <button type="button" onClick={() => run('DELETE')} disabled={busy} className="btn-link">
              Turn off link
            </button>
          </>
        ) : (
          <button type="button" onClick={() => run('POST')} disabled={busy} className="btn-secondary px-3 py-1">
            Create a read-only link
          </button>
        )}
      </div>
      <p className="text-slate-500">
        {note || 'The link shows your answers and scores, read-only. You can turn it off any time.'}
      </p>
    </div>
  )
}

export function SharedReport() {
  const { token } = useParams()
  const [report, setReport] = useState(null)
  const [error, setError] = useState('')
  useEffect(() => {
    api(`/shared/reports/${token}`)
      .then((data) => setReport(data.report))
      .catch((err) => setError(err.message))
  }, [token])
  return (
    <PublicShell>
      {report ? (
        <ReportView report={report} shared />
      ) : error ? (
        <p role="alert" className="text-red-600">
          {error}
        </p>
      ) : (
        <p className="animate-pulse text-slate-500">Loading the report…</p>
      )}
    </PublicShell>
  )
}

export default function Report() {
  const { id } = useParams()
  const { user } = useAuth()
  const [report, setReport] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const build = useCallback(async () => {
    setError('')
    setBusy(true)
    try {
      setReport((await api(`/sessions/${id}/report`, { method: 'POST' })).report)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }, [id])

  useEffect(() => {
    let cancelled = false
    api(`/sessions/${id}/report`)
      .then((data) => !cancelled && setReport(data.report))
      .catch((err) => {
        if (cancelled) return
        if (err.status === 404) build()
        else setError(err.message)
      })
    return () => {
      cancelled = true
    }
  }, [id, build])

  const generating = report?.status === 'generating'
  useEffect(() => {
    if (!generating) return
    const t = setTimeout(() => {
      api(`/sessions/${id}/report`)
        .then((data) => setReport(data.report))
        .catch((err) => setError(err.message))
    }, POLL_MS)
    return () => clearTimeout(t)
  }, [id, generating, report])

  function onAttempt(questionId, attempt) {
    setReport((r) => ({
      ...r,
      questions: r.questions.map((q) =>
        q.question_id === questionId ? { ...q, attempts: [...q.attempts, attempt] } : q,
      ),
    }))
  }

  if (!report) {
    return error ? (
      <div className="space-y-3">
        <p role="alert" className="text-red-600">
          {error}
        </p>
        <Link to={`/interview/${id}`} className="text-sm text-brand-700 underline">
          Back to the interview
        </Link>
      </div>
    ) : (
      <p className="animate-pulse text-slate-500">Preparing your report…</p>
    )
  }

  return (
    <>
      {hasOrgs(user) && <CoachComments sessionId={id} />}
      <ReportView report={report} id={id} onAttempt={onAttempt} build={build} busy={busy} error={error} />
    </>
  )
}

// Comments from the candidate's coach (T-166); nothing when there are none.
function CoachComments({ sessionId }) {
  const [comments, setComments] = useState([])
  useEffect(() => {
    api(`/orgs/mine/sessions/${sessionId}/comments`)
      .then((data) => setComments(data.comments))
      .catch(() => setComments([]))
  }, [sessionId])
  if (!comments.length) return null
  return (
    <section className="card mb-6 space-y-3 p-6 print:hidden" aria-labelledby="coach-notes">
      <h2 id="coach-notes" className="text-lg font-bold">
        From your coach
      </h2>
      <CommentList comments={comments} />
    </section>
  )
}

export function ReportView({ report, id, onAttempt, build, busy, error, shared = false, title = '' }) {
  const { scored, total, set_aside: setAside = 0 } = report.progress
  const generating = report.status === 'generating'
  return (
    <section className="space-y-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="eyebrow">
            {report.debrief
              ? 'Debrief of a real interview'
              : report.negotiation
                ? 'Negotiation report'
                : report.panel
                  ? 'Panel interview report'
                  : 'Interview report'}
          </p>
          <h1 className="mt-1 text-3xl font-extrabold text-slate-900">
            {report.debrief
              ? `${report.debrief.role}${report.debrief.company ? ` at ${report.debrief.company}` : ''}`
              : title ||
                (shared ? 'Shared interview report' : 'Your report')}
          </h1>
          <p className="mt-1 text-slate-600">
            {report.role_title} · {report.duration_min} minutes · {report.difficulty}
          </p>
          {report.negotiation && (
            <p className="mt-1 text-sm text-slate-500">
              Offer {report.negotiation.offer} · your target {report.negotiation.target}
            </p>
          )}
        </div>
        <div className="flex gap-3 text-sm print:hidden">
          {!shared && (
            <Link to={`/interview/${id}`} className="btn-secondary">
              Transcript
            </Link>
          )}
          {report.status === 'ready' && !shared && (
            <Link to={`/report/${id}/cheatsheet`} className="btn-secondary">
              <span aria-hidden="true">📄</span>Cheat sheet
            </Link>
          )}
          <button type="button" onClick={() => window.print()} className="btn-secondary">
            Print / save as PDF
          </button>
        </div>
      </header>

      <p className="rounded-xl bg-surface/70 p-3 text-sm text-slate-600 ring-1 ring-slate-200">
        Scores are practice feedback from an AI coach, not a hiring assessment.
        {report.licensed_field &&
          ' For licensed or specialized professions, they are not a professional evaluation of your competence.'}
      </p>

      {generating && (
        <p role="status" className="animate-pulse text-slate-600">
          Scoring your answers… {scored} of {total} questions done.
        </p>
      )}
      {report.status === 'ready' && total > 0 && !shared && (
        <ShareReport sessionId={report.session_id} token={report.share_token} />
      )}
      {report.status === 'ready' && setAside > 0 && (
        <p role="note" className="rounded-md bg-brand-50 p-3 text-sm text-slate-700">
          {setAside === 1 ? '1 question' : `${setAside} questions`} couldn't be scored, so the report covers the other{' '}
          {scored}.
        </p>
      )}
      {report.status === 'failed' && !shared && (
        <div role="alert" className="rounded-md bg-red-50 p-3 text-sm text-red-700">
          Part of the report couldn't be generated ({scored} of {total} questions scored).{' '}
          <button type="button" onClick={build} disabled={busy} className="font-medium underline">
            {busy ? 'Retrying…' : 'Finish the report'}
          </button>
        </div>
      )}
      {error && (
        <p role="alert" className="text-sm text-red-600">
          {error}
        </p>
      )}
      {total === 0 && !generating && <p className="text-slate-600">You didn't answer any questions, so there's nothing to score.</p>}

      {report.debrief && <NoRecordingsNotice />}
      {report.status === 'ready' && total > 0 && !shared && <ThankYou sessionId={report.session_id} />}
      {report.status === 'ready' && total > 0 && <Summary report={report} />}
      {report.debrief && report.status === 'ready' && !shared && <NextRound debrief={report.debrief} />}
      {report.debrief && !shared && <DebriefKeep debrief={report.debrief} />}

      <div className="space-y-4">
        {report.questions.map((q, i) => (
          <QuestionCard
            key={q.question_id}
            q={q}
            index={i}
            sessionId={report.session_id}
            onAttempt={onAttempt}
            failed={report.status === 'failed'}
            shared={shared}
          />
        ))}
      </div>

      {report.unanswered?.length > 0 && (
        <div className="card p-6">
          <h2 className="text-lg font-bold">Questions you didn't get to</h2>
          <p className="text-sm text-slate-500">
            Not scored. Practice them in your next interview.
          </p>
          <ul className="mt-3 space-y-2 text-sm">
            {report.unanswered.map((u) => (
              <li key={u.text} className="flex gap-2">
                <span aria-hidden="true" className="text-slate-400">○</span>
                <span>
                  {u.text}
                  <span className="text-slate-500">
                    {' '}
                    · {u.section}
                    {u.asked ? ' · asked, not answered' : ''}
                  </span>
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  )
}
