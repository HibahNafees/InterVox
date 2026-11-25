import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { HeroScene, IconTile, Mascot } from '../components/Art'
import Assignments from '../components/Assignments'
import { useDialogs } from '../components/ConfirmDialog'
import ScoreChart from '../components/ScoreChart'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'

// "Your interviews" shows this many when collapsed; the choice is kept per browser (T-137).
const COLLAPSED_COUNT = 3
const LIST_KEY = 'mi_interviews_expanded'

function listExpandedPref() {
  try {
    return localStorage.getItem(LIST_KEY) !== '0'
  } catch {
    return true // Storage unavailable: the full list.
  }
}

function setListExpandedPref(expanded) {
  try {
    if (expanded) localStorage.removeItem(LIST_KEY)
    else localStorage.setItem(LIST_KEY, '0')
  } catch {
    // Storage unavailable: the choice lasts for this page only.
  }
}

const STATUS = {
  planned: ['Plan ready', 'bg-navy-100 text-navy-700'],
  active: ['In progress', 'bg-accent-100 text-accent-700'],
  completed: ['Report', 'bg-emerald-100 text-emerald-700'],
  abandoned: ['Cancelled', 'bg-slate-100 text-slate-500'],
}

// Interviews that aren't regular practice interviews get their own label.
const MODE_LABEL = {
  reverse: ['You interviewed', 'bg-accent-100 text-accent-700'],
  debrief: ['Debrief', 'bg-navy-100 text-navy-700'],
  negotiation: ['Negotiation', 'bg-emerald-100 text-emerald-700'],
}

const TIPS = [
  'Lead with the answer in one sentence, then give the story behind it.',
  'Numbers stick: "cut load time from 4 s to 1 s" beats "made it faster".',
  'A short pause before answering sounds confident, not unsure.',
  'For "Tell me about a time…", use Situation, Task, Action, Result.',
  'End each answer with what you learned or what changed because of you.',
  "It's fine to say \"Let me think about that for a second.\"",
  'Prepare three stories that show different strengths; most questions fit one.',
]

const STEPS = [
  ['📄', 'Add your résumé and the job', 'Paste or upload both; we work out the role and what it needs.', 'brand'],
  ['🎙️', 'Answer out loud', 'A timed interview that adapts to what you say, like the real thing.', 'accent'],
  ['📈', 'Get a scored report', 'Scores, weak moments, and a stronger version of every answer.', 'navy'],
]

function fmt(score) {
  return score == null ? '–' : score.toFixed(1)
}

function scoreTone(s) {
  if (s == null) return 'bg-slate-100 text-slate-500'
  if (s >= 4) return 'bg-emerald-100 text-emerald-700'
  if (s >= 3) return 'bg-accent-100 text-accent-700'
  return 'bg-brand-100 text-brand-700'
}

function Stat({ icon, tone, label, value, sub }) {
  return (
    <div className="card flex items-center gap-4 p-5">
      <IconTile tone={tone}>{icon}</IconTile>
      <div className="min-w-0">
        <p className="text-sm font-medium text-slate-500">{label}</p>
        <p className="font-display text-2xl font-extrabold text-ink tabular-nums">{value}</p>
        {sub && <p className="truncate text-xs text-slate-500">{sub}</p>}
      </div>
    </div>
  )
}

function LevelCard({ s }) {
  return (
    <div className="card space-y-4 p-6">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-bold">Your level</h2>
        <span className="chip bg-accent-100 text-accent-700">
          <span aria-hidden="true">🔥</span>
          {s.streak_days} day{s.streak_days === 1 ? '' : 's'} streak
        </span>
      </div>
      <p className="font-display text-4xl font-extrabold text-ink">
        Level {s.level}
        <span className="text-base font-semibold text-slate-400"> / 10</span>
      </p>
      <div className="flex gap-1" aria-hidden="true">
        {Array.from({ length: 10 }, (_, i) => (
          <span
            key={i}
            className={`h-2.5 flex-1 rounded-full ${i < s.level ? 'bg-gradient-to-r from-brand-400 to-accent-400' : 'bg-line-soft'}`}
          />
        ))}
      </div>
      <p className="text-sm text-slate-600">
        {s.next_level_in == null
          ? 'Top level reached. Keep practicing to stay sharp!'
          : `${s.next_level_in} more interview${s.next_level_in === 1 ? '' : 's'} to reach level ${s.level + 1}.`}
      </p>
      <dl className="grid grid-cols-2 gap-3 border-t border-line-soft pt-4 text-sm">
        <div>
          <dt className="text-slate-500">Questions answered</dt>
          <dd className="font-bold text-ink tabular-nums">{s.questions_answered}</dd>
        </div>
        <div>
          <dt className="text-slate-500">Answers retried</dt>
          <dd className="font-bold text-ink tabular-nums">{s.retries}</dd>
        </div>
      </dl>
    </div>
  )
}

function PracticeCard({ practice }) {
  const navigate = useNavigate()
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const queued = practice.due + practice.upcoming

  async function start() {
    setError('')
    setBusy(true)
    try {
      const { session } = await api('/sessions/practice', { method: 'POST', body: { duration_min: 10 } })
      navigate(`/interview/${session.id}`)
    } catch (err) {
      setError(err.message)
      setBusy(false)
    }
  }

  return (
    <div className="card flex flex-col gap-4 p-6">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-bold">Practice queue</h2>
          <p className="text-sm text-slate-500">Questions you scored under 4 come back to practice</p>
        </div>
        <IconTile tone="brand">🔁</IconTile>
      </div>
      <dl className="grid grid-cols-3 gap-3 text-center">
        {[
          ['Due now', practice.due, 'text-brand-700'],
          ['Coming up', practice.upcoming, 'text-ink'],
          ['Mastered', practice.mastered, 'text-emerald-700'],
        ].map(([label, n, tone]) => (
          <div key={label} className="rounded-2xl bg-sand p-3">
            <dt className="text-xs font-medium text-slate-500">{label}</dt>
            <dd className={`font-display text-2xl font-extrabold tabular-nums ${tone}`}>{n}</dd>
          </div>
        ))}
      </dl>
      <button type="button" onClick={start} disabled={busy || queued === 0} className="btn-primary self-start">
        {busy ? 'Building your practice…' : 'Practice my weak spots'}
      </button>
      {queued === 0 && <p className="text-xs text-slate-500">Nothing queued yet. Nice work!</p>}
      {error && (
        <p role="alert" className="text-sm text-red-600">
          {error}
        </p>
      )}
    </div>
  )
}

function GoalCard({ goal, onChange }) {
  const pct = Math.min(100, (goal.done_this_week / goal.weekly) * 100)
  const met = goal.done_this_week >= goal.weekly

  async function set(weekly) {
    if (weekly < 1 || weekly > 14) return
    const data = await api('/stats/goal', { method: 'PUT', body: { weekly_goal: weekly } })
    onChange(data.stats)
  }

  return (
    <div className="card flex flex-col gap-4 p-6">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-bold">This week's goal</h2>
          <p className="text-sm text-slate-500">Practice interviews completed since Monday</p>
        </div>
        <IconTile tone="green">🎯</IconTile>
      </div>
      <p className="font-display text-4xl font-extrabold text-ink tabular-nums">
        {goal.done_this_week}
        <span className="text-lg font-semibold text-slate-400"> / {goal.weekly}</span>
      </p>
      <div className="h-3 overflow-hidden rounded-full bg-line-soft" aria-hidden="true">
        <div className="h-full rounded-full bg-gradient-to-r from-emerald-400 to-teal-500" style={{ width: `${pct}%` }} />
      </div>
      <p className="text-sm text-slate-600">
        {met ? 'Goal reached this week. Great consistency!' : `${goal.weekly - goal.done_this_week} more to reach your goal.`}
      </p>
      <div className="flex items-center gap-3 text-sm">
        <span className="text-slate-500">Weekly goal</span>
        <button type="button" aria-label="Lower weekly goal" onClick={() => set(goal.weekly - 1)} className="btn-secondary px-3 py-1">
          −
        </button>
        <span className="font-semibold tabular-nums">{goal.weekly}</span>
        <button type="button" aria-label="Raise weekly goal" onClick={() => set(goal.weekly + 1)} className="btn-secondary px-3 py-1">
          +
        </button>
      </div>
    </div>
  )
}

export default function Dashboard() {
  const { user } = useAuth()
  const [sessions, setSessions] = useState([])
  const [stats, setStats] = useState(null)
  const [expanded, setExpanded] = useState(listExpandedPref)
  const { confirm, notify } = useDialogs()
  const [tip] = useState(() => TIPS[Math.floor(Math.random() * TIPS.length)])
  const first = user.name.split(' ')[0]

  function loadStats() {
    api('/stats')
      .then((data) => setStats(data.stats))
      .catch(() => {})
  }

  useEffect(() => {
    api('/sessions')
      .then((data) => setSessions(data.sessions ?? []))
      .catch(() => {})
    loadStats()
  }, [])

  function toggleList(next = !expanded) {
    setExpanded(next)
    setListExpandedPref(next)
  }

  async function removeSession(x) {
    const deleted = await confirm({
      title: 'Delete this interview?',
      message: `“${x.role_title || 'Interview'}” and its answers and report will be permanently deleted. This can’t be undone.`,
      confirmLabel: 'Delete',
      busyLabel: 'Deleting…',
      danger: true,
      onConfirm: () => api(`/sessions/${x.id}`, { method: 'DELETE' }),
    })
    if (!deleted) return
    setSessions((all) => all.filter((y) => y.id !== x.id))
    notify('Interview deleted')
    loadStats()
  }


  const s = stats
  const hasScores = s?.history?.length > 0
  return (
    <section className="space-y-8">
      <div className="relative overflow-hidden rounded-[2rem] border border-blush bg-gradient-to-br from-brand-50 via-surface to-accent-50 p-8 sm:p-10">
        <div className="grid items-center gap-6 md:grid-cols-[1fr_18rem]">
          <div>
            <p className="eyebrow">AI voice practice interviews for any job</p>
            <h1 className="mt-2 text-4xl font-extrabold sm:text-5xl">
              Welcome, {first} <span aria-hidden="true">👋</span>
            </h1>
            <p className="mt-3 max-w-xl text-lg text-slate-600">
              Practice for any job: upload your résumé and a job description, answer out loud,
              and get a scored report with stronger versions of your answers.
            </p>
            <div className="mt-6 flex flex-wrap items-center gap-3">
              <Link to="/setup" className="btn-primary px-6 py-3 text-base">
                Start a practice interview <span aria-hidden="true">🚀</span>
              </Link>
              {s && s.interviews > 0 && (
                <span className="chip bg-surface text-slate-700 ring-1 ring-line">
                  Level {s.level} · {s.interviews} interview{s.interviews === 1 ? '' : 's'} done
                </span>
              )}
            </div>
          </div>
          <HeroScene className="hidden h-60 md:block" />
        </div>
      </div>

      <Assignments />

      {s && s.interviews > 0 ? (
        <>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Stat icon="🎯" tone="brand" label="Practice interviews" value={s.interviews} sub={`${s.started} started`} />
            <Stat icon="⭐" tone="accent" label="Average score" value={`${fmt(s.average_score)} / 5`} sub={s.latest_score != null ? `Latest ${fmt(s.latest_score)}` : null} />
            <Stat icon="🏆" tone="green" label="Best score" value={`${fmt(s.best_score)} / 5`} />
            <Stat icon="⏱️" tone="navy" label="Time practicing" value={`${s.practice_minutes} min`} sub={`${s.questions_answered} questions answered`} />
          </div>

          <div className="grid gap-4 lg:grid-cols-[1fr_20rem]">
            <div className="card p-6">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
                  <h2 className="text-lg font-bold">Your score over time</h2>
                  <p className="text-sm text-slate-500">Overall score of each interview, out of 5</p>
                </div>
                {s.improvement != null && (
                  <span className={`chip ${s.improvement >= 0 ? 'bg-emerald-100 text-emerald-700' : 'bg-brand-100 text-brand-700'}`}>
                    {s.improvement >= 0 ? '▲ +' : '▼ '}
                    {s.improvement.toFixed(1)} since your first
                  </span>
                )}
              </div>
              {hasScores ? (
                <div className="mt-4">
                  <ScoreChart history={s.history} />
                </div>
              ) : (
                <p className="mt-6 text-sm text-slate-500">Open a report to see your first score here.</p>
              )}
            </div>
            <LevelCard s={s} />
          </div>

          {s.practice && s.goal && (
            <div className="grid gap-4 lg:grid-cols-2">
              <PracticeCard practice={s.practice} />
              <GoalCard goal={s.goal} onChange={setStats} />
            </div>
          )}

          <div className="grid gap-4 lg:grid-cols-2">
            <div className="card p-6">
              <h2 className="text-lg font-bold">Roles you've practiced</h2>
              <ul className="mt-4 space-y-3">
                {s.roles.map((r) => (
                  <li key={r.role} className="flex items-center justify-between gap-3">
                    <span className="flex min-w-0 items-center gap-3">
                      <IconTile tone="navy" className="h-9 w-9 text-sm font-bold text-navy-800">
                        {r.role[0]}
                      </IconTile>
                      <span className="min-w-0">
                        <span className="block truncate font-semibold text-ink">{r.role}</span>
                        <span className="text-xs text-slate-500">
                          {r.interviews} interview{r.interviews === 1 ? '' : 's'}
                        </span>
                      </span>
                    </span>
                    <span className={`chip tabular-nums ${scoreTone(r.average_score)}`}>
                      {fmt(r.average_score)} / 5
                    </span>
                  </li>
                ))}
              </ul>
            </div>
            <div className="card p-6">
              <h2 className="text-lg font-bold">Your skills</h2>
              <p className="text-sm text-slate-500">Average across your answers, and change since your first interview</p>
              {s.skills.length ? (
                <ul className="mt-4 space-y-3">
                  {s.skills.map((k) => (
                    <li key={k.name}>
                      <div className="flex items-baseline justify-between gap-2 text-sm">
                        <span className="font-medium text-slate-700">{k.name}</span>
                        <span className="flex items-baseline gap-2">
                          {k.change != null && k.change !== 0 && (
                            <span
                              className={`text-xs font-semibold tabular-nums ${k.change > 0 ? 'text-emerald-700' : 'text-brand-700'}`}
                            >
                              {k.change > 0 ? '▲ +' : '▼ '}
                              {k.change.toFixed(1)}
                            </span>
                          )}
                          <span className="font-bold text-ink tabular-nums">{fmt(k.score)}</span>
                        </span>
                      </div>
                      <div className="mt-1 h-2 overflow-hidden rounded-full bg-line-soft" aria-hidden="true">
                        <div
                          className="h-full rounded-full bg-gradient-to-r from-brand-400 to-accent-400"
                          style={{ width: `${(k.score / 5) * 100}%` }}
                        />
                      </div>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-4 text-sm text-slate-500">Your skills appear after your first report.</p>
              )}
            </div>
          </div>
        </>
      ) : (
        <ol className="grid gap-4 sm:grid-cols-3">
          {STEPS.map(([icon, title, text, tone], i) => (
            <li key={title} className="card p-6">
              <IconTile tone={tone}>{icon}</IconTile>
              <p className="mt-4 text-xs font-bold text-slate-400">STEP {i + 1}</p>
              <h2 className="mt-1 text-lg font-bold">{title}</h2>
              <p className="mt-1 text-sm text-slate-600">{text}</p>
            </li>
          ))}
        </ol>
      )}

      <div className="flex items-center gap-4 rounded-3xl bg-night p-6 text-white">
        <Mascot className="h-20 w-20 shrink-0" />
        <div>
          <p className="text-xs font-bold tracking-wider text-accent-300 uppercase">Tip of the day</p>
          <p className="mt-1 text-lg font-semibold">{tip}</p>
        </div>
      </div>

      {sessions.length > 0 && (
        <div>
          <div className="flex items-center justify-between gap-3">
            <h2 id="your-interviews" className="text-xl font-bold">
              Your interviews
            </h2>
            {sessions.length > COLLAPSED_COUNT && (
              <button
                type="button"
                onClick={() => toggleList()}
                aria-expanded={expanded}
                aria-controls="interview-list"
                className="btn-secondary"
              >
                {expanded ? 'Show less' : 'Show more'}
                <span aria-hidden="true" className={`transition ${expanded ? 'rotate-180' : ''}`}>
                  ▾
                </span>
              </button>
            )}
          </div>
          <ul
            id="interview-list"
            aria-labelledby="your-interviews"
            className="card mt-3 divide-y divide-line-soft overflow-hidden"
          >
            {(expanded ? sessions : sessions.slice(0, COLLAPSED_COUNT)).map((x) => {
              const [label, color] = MODE_LABEL[x.mode] ?? STATUS[x.status] ?? [x.status, 'bg-slate-100 text-slate-600']
              return (
                <li key={x.id} className="flex items-center hover:bg-brand-50/60">
                  <Link
                    to={
                      x.mode === 'reverse'
                        ? `/reverse/${x.id}`
                        : x.status === 'completed'
                          ? `/report/${x.id}`
                          : `/interview/${x.id}`
                    }
                    className="flex min-w-0 flex-1 items-center justify-between gap-3 py-4 pl-5"
                  >
                    <span className="flex min-w-0 items-center gap-3">
                      <IconTile tone="brand" className="h-10 w-10 font-bold text-brand-700">
                        {(x.role_title || 'I')[0]}
                      </IconTile>
                      <span className="min-w-0">
                        <span className="block truncate font-semibold text-ink">{x.role_title || 'Interview'}</span>
                        <span className="text-sm text-slate-500">
                          {x.duration_min} min · {new Date(x.created_at).toLocaleDateString()}
                        </span>
                      </span>
                    </span>
                    <span className={`chip ${color}`}>{label}</span>
                  </Link>
                  <button
                    type="button"
                    onClick={() => removeSession(x)}
                    aria-label={`Delete the interview ${x.role_title || 'Interview'}`}
                    className="btn-link shrink-0 px-5 text-sm hover:text-red-600"
                  >
                    Delete
                  </button>
                </li>
              )
            })}
          </ul>
          {!expanded && sessions.length > COLLAPSED_COUNT && (
            <div className="mt-3 text-center">
              <button type="button" onClick={() => toggleList(true)} className="btn-link">
                Show all ({sessions.length})
              </button>
            </div>
          )}
        </div>
      )}
    </section>
  )
}
