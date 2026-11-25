import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useDialogs } from '../components/ConfirmDialog'
import NotFound from '../components/NotFound'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { brandStyle, staffOrg } from '../lib/orgs'

function fmt(score) {
  return score == null ? '–' : score.toFixed(1)
}

// A tiny trend line of overall scores (1–5), oldest to newest.
export function Sparkline({ scores, label }) {
  if (!scores?.length) return <span className="text-slate-400">–</span>
  const w = 80
  const h = 24
  const x = (i) => (scores.length === 1 ? w / 2 : (i * (w - 4)) / (scores.length - 1) + 2)
  const y = (s) => 2 + ((5 - s) / 4) * (h - 4)
  const d = scores.map((s, i) => `${i ? 'L' : 'M'}${x(i)},${y(s)}`).join(' ')
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="h-6 w-20" role="img" aria-label={label}>
      <path d={d} fill="none" stroke="var(--org)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx={x(scores.length - 1)} cy={y(scores[scores.length - 1])} r="2.5" fill="var(--org)" />
    </svg>
  )
}

export function OrgHeader({ org, title, eyebrow, children }) {
  return (
    <header className="flex flex-wrap items-center gap-4" style={brandStyle(org)}>
      {org.logo ? (
        <img src={org.logo} alt={`${org.name} logo`} className="h-14 w-14 rounded-2xl" />
      ) : (
        <span className="grid h-14 w-14 place-items-center rounded-2xl text-xl font-bold text-white" style={{ background: 'var(--org)' }}>
          {org.name[0]}
        </span>
      )}
      <div className="min-w-0 flex-1">
        <p className="text-xs font-bold tracking-wider uppercase" style={{ color: 'var(--org)' }}>
          {eyebrow ?? org.name}
          {org.is_demo && <span className="chip ml-2 bg-amber-100 text-amber-800 normal-case">Demo</span>}
        </p>
        <h1 className="mt-1 text-3xl font-extrabold text-slate-900">{title}</h1>
      </div>
      {children}
    </header>
  )
}

function AssignDialog({ org, candidates, onClose, onDone }) {
  const [form, setForm] = useState({
    candidate_id: candidates[0]?.id ?? '',
    role_title: '',
    jd_text: '',
    duration_min: 30,
    due_date: '',
  })
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }))

  async function submit(e) {
    e.preventDefault()
    setError('')
    setBusy(true)
    try {
      await api(`/orgs/${org.id}/assignments`, {
        method: 'POST',
        body: {
          ...form,
          candidate_id: Number(form.candidate_id),
          duration_min: Number(form.duration_min),
          due_date: form.due_date || null,
        },
      })
      onDone()
    } catch (err) {
      setError(err.message)
      setBusy(false)
    }
  }

  return (
    <div className="fixed inset-0 z-30 grid place-items-center bg-night/40 p-4" role="dialog" aria-modal="true" aria-labelledby="assign-title">
      <form onSubmit={submit} className="card max-h-[90vh] w-full max-w-lg space-y-4 overflow-y-auto p-6">
        <h2 id="assign-title" className="text-xl font-bold">
          Assign an interview
        </h2>
        <label className="block space-y-1 text-sm font-medium">
          <span>Candidate</span>
          <select className="field" value={form.candidate_id} onChange={set('candidate_id')}>
            {candidates.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </label>
        <label className="block space-y-1 text-sm font-medium">
          <span>Role</span>
          <input className="field" required maxLength={160} value={form.role_title} onChange={set('role_title')} placeholder="e.g. Customer Success Manager" />
        </label>
        <label className="block space-y-1 text-sm font-medium">
          <span>Job description</span>
          <textarea className="field min-h-32" required minLength={20} value={form.jd_text} onChange={set('jd_text')} />
        </label>
        <div className="grid grid-cols-2 gap-3">
          <label className="block space-y-1 text-sm font-medium">
            <span>Length (minutes)</span>
            <input className="field" type="number" min={5} max={60} required value={form.duration_min} onChange={set('duration_min')} />
          </label>
          <label className="block space-y-1 text-sm font-medium">
            <span>Due date</span>
            <input className="field" type="date" value={form.due_date} onChange={set('due_date')} />
          </label>
        </div>
        {error && (
          <p role="alert" className="text-sm text-red-600">
            {error}
          </p>
        )}
        <div className="flex justify-end gap-3">
          <button type="button" className="btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button className="btn-primary" disabled={busy}>
            {busy ? 'Assigning…' : 'Assign'}
          </button>
        </div>
      </form>
    </div>
  )
}

export default function Coach() {
  const { user } = useAuth()
  const { notify } = useDialogs()
  const mine = staffOrg(user)
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [assigning, setAssigning] = useState(false)
  const [invite, setInvite] = useState('')

  const load = useCallback(() => {
    if (!mine) return
    api(`/orgs/${mine.id}/candidates`)
      .then(setData)
      .catch((err) => setError(err.message))
  }, [mine])

  useEffect(load, [load])

  if (!mine) return <NotFound />
  if (error) {
    return (
      <p role="alert" className="text-red-600">
        {error}
      </p>
    )
  }
  if (!data) return <p className="animate-pulse text-slate-500">Loading candidates…</p>

  const { org, candidates } = data
  const shared = candidates.filter((c) => c.consent)
  const flagged = shared.filter((c) => c.needs_practice.length)

  async function makeInvite() {
    try {
      const { token } = await api(`/orgs/${org.id}/invites`, { method: 'POST' })
      setInvite(`${window.location.origin}/join/${token}`)
    } catch (err) {
      notify(err.message)
    }
  }

  return (
    <section className="space-y-6" style={brandStyle(org)}>
      <OrgHeader org={org} title="Your candidates">
        <div className="flex flex-wrap gap-2">
          <button className="btn-secondary" onClick={makeInvite}>
            Invite a candidate
          </button>
          <button
            className="inline-flex items-center rounded-full px-5 py-2.5 font-semibold text-white"
            style={{ background: 'var(--org)' }}
            onClick={() => setAssigning(true)}
            disabled={!candidates.length}
          >
            Assign an interview
          </button>
          {org.role === 'admin' && (
            <Link to={`/org/${org.id}/settings`} className="btn-link self-center">
              Branding
            </Link>
          )}
        </div>
      </OrgHeader>

      {invite && (
        <div className="card flex flex-wrap items-center gap-3 p-4 text-sm">
          <span className="font-medium">Invite link (valid 14 days):</span>
          <input readOnly value={invite} className="field flex-1 py-1.5 text-sm" aria-label="Invite link" onFocus={(e) => e.target.select()} />
          <button
            className="btn-secondary"
            onClick={() => navigator.clipboard?.writeText(invite).then(() => notify('Link copied'), () => {})}
          >
            Copy
          </button>
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-3">
        <div className="card p-5">
          <p className="text-sm text-slate-500">Candidates</p>
          <p className="text-3xl font-extrabold tabular-nums">{candidates.length}</p>
          <p className="text-xs text-slate-500">{shared.length} sharing their reports</p>
        </div>
        <div className="card p-5">
          <p className="text-sm text-slate-500">Needs practice</p>
          <p className="text-3xl font-extrabold tabular-nums text-red-700">{flagged.length}</p>
        </div>
        <div className="card p-5">
          <p className="text-sm text-slate-500">Open assignments</p>
          <p className="text-3xl font-extrabold tabular-nums">
            {shared.reduce((n, c) => n + (c.assignments_open || 0), 0)}
          </p>
        </div>
      </div>

      <div className="card overflow-x-auto p-2 sm:p-4">
        <table className="w-full text-left text-sm">
          <thead className="text-slate-500">
            <tr>
              <th className="px-3 py-2 font-medium">Candidate</th>
              <th className="px-3 py-2 font-medium">Latest</th>
              <th className="px-3 py-2 font-medium">Trend</th>
              <th className="hidden px-3 py-2 font-medium md:table-cell">Weak areas</th>
              <th className="px-3 py-2 font-medium">Status</th>
            </tr>
          </thead>
          <tbody>
            {candidates.map((c) => (
              <tr key={c.id} className="border-t border-line-soft align-top">
                <td className="px-3 py-3">
                  {c.consent ? (
                    <Link to={`/coach/${org.id}/candidates/${c.id}`} className="font-semibold text-slate-900 hover:underline">
                      {c.name}
                    </Link>
                  ) : (
                    <span className="font-semibold text-slate-900">{c.name}</span>
                  )}
                  {c.role && <p className="text-xs text-slate-500">{c.role}</p>}
                </td>
                {c.consent ? (
                  <>
                    <td className="px-3 py-3 font-bold tabular-nums">{fmt(c.latest_score)}</td>
                    <td className="px-3 py-3">
                      <Sparkline scores={c.trend} label={`Scores: ${c.trend.map(fmt).join(', ')}`} />
                      {c.improvement != null && (
                        <p className={`text-xs ${c.improvement >= 0 ? 'text-emerald-700' : 'text-red-700'}`}>
                          {c.improvement >= 0 ? '+' : ''}
                          {c.improvement.toFixed(1)} since first
                        </p>
                      )}
                    </td>
                    <td className="hidden px-3 py-3 md:table-cell">
                      <div className="flex flex-wrap gap-1">
                        {c.weak_areas.length ? (
                          c.weak_areas.map((w) => (
                            <span key={w} className="chip bg-slate-100 text-slate-700">
                              {w}
                            </span>
                          ))
                        ) : (
                          <span className="text-slate-400">None</span>
                        )}
                      </div>
                    </td>
                    <td className="px-3 py-3">
                      {c.needs_practice.length ? (
                        <span className="chip bg-red-100 text-red-800" title={c.needs_practice.join(' · ')}>
                          Needs practice
                        </span>
                      ) : (
                        <span className="chip bg-emerald-100 text-emerald-800">On track</span>
                      )}
                      {c.needs_practice.length > 0 && <p className="mt-1 text-xs text-slate-500">{c.needs_practice.join(' · ')}</p>}
                    </td>
                  </>
                ) : (
                  <td colSpan={4} className="px-3 py-3 text-slate-500">
                    Waiting for consent: their reports stay private until they share them.
                  </td>
                )}
              </tr>
            ))}
            {!candidates.length && (
              <tr>
                <td colSpan={5} className="px-3 py-6 text-center text-slate-500">
                  No candidates yet. Send an invite link to get started.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-slate-500">
        Scores are practice feedback from an AI interviewer, not hiring assessments.
      </p>

      {assigning && (
        <AssignDialog
          org={org}
          candidates={candidates}
          onClose={() => setAssigning(false)}
          onDone={() => {
            setAssigning(false)
            notify('Interview assigned')
            load()
          }}
        />
      )}
    </section>
  )
}
