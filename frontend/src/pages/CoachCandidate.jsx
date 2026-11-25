import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import ScoreChart from '../components/ScoreChart'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { STATUS_LABELS, brandStyle, fmtDate, staffOrg } from '../lib/orgs'
import { OrgHeader } from './Coach'

function fmt(score) {
  return score == null ? '–' : score.toFixed(1)
}

export default function CoachCandidate() {
  const { orgId, candidateId } = useParams()
  const { user } = useAuth()
  const org = staffOrg(user)
  const [c, setC] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    api(`/orgs/${orgId}/candidates/${candidateId}`)
      .then((data) => setC(data.candidate))
      .catch((err) => setError(err.message))
  }, [orgId, candidateId])

  if (error) {
    return (
      <p role="alert" className="text-red-600">
        {error}
      </p>
    )
  }
  if (!c || !org) return <p className="animate-pulse text-slate-500">Loading…</p>
  const s = c.stats

  return (
    <section className="space-y-6" style={brandStyle(org)}>
      <Link to="/coach" className="btn-link">
        ← All candidates
      </Link>
      <OrgHeader org={org} title={c.name} eyebrow={`${org.name} · candidate`} />

      <div className="grid gap-4 sm:grid-cols-4">
        <div className="card p-5">
          <p className="text-sm text-slate-500">Latest score</p>
          <p className="text-3xl font-extrabold tabular-nums">{fmt(s.latest_score)}</p>
          {s.improvement != null && (
            <p className={`text-xs ${s.improvement >= 0 ? 'text-emerald-700' : 'text-red-700'}`}>
              {s.improvement >= 0 ? '+' : ''}
              {s.improvement.toFixed(1)} since first
            </p>
          )}
        </div>
        <div className="card p-5">
          <p className="text-sm text-slate-500">Interviews</p>
          <p className="text-3xl font-extrabold tabular-nums">{s.interviews}</p>
          <p className="text-xs text-slate-500">Level {s.level}</p>
        </div>
        <div className="card p-5">
          <p className="text-sm text-slate-500">Streak</p>
          <p className="text-3xl font-extrabold tabular-nums">{s.streak_days} days</p>
        </div>
        <div className="card p-5">
          <p className="text-sm text-slate-500">Weekly goal</p>
          <p className="text-3xl font-extrabold tabular-nums">
            {s.goal.done_this_week}/{s.goal.weekly}
          </p>
        </div>
      </div>

      {s.history.length > 0 && (
        <div className="card p-6">
          <h2 className="text-lg font-bold">Score over time</h2>
          <ScoreChart history={s.history} />
        </div>
      )}

      <div className="grid gap-4 md:grid-cols-2">
        <div className="card p-6">
          <h2 className="text-lg font-bold">Skills</h2>
          <ul className="mt-3 space-y-2 text-sm">
            {s.skills.map((k) => (
              <li key={k.name} className="flex items-center justify-between gap-3">
                <span className={c.weak_areas.includes(k.name) ? 'font-semibold text-red-700' : ''}>{k.name}</span>
                <span className="tabular-nums">{fmt(k.score)}</span>
              </li>
            ))}
          </ul>
        </div>
        <div className="card p-6">
          <h2 className="text-lg font-bold">Assignments</h2>
          {c.assignments.length === 0 ? (
            <p className="mt-2 text-sm text-slate-500">None yet.</p>
          ) : (
            <ul className="mt-3 space-y-2 text-sm">
              {c.assignments.map((a) => (
                <li key={a.id} className="flex items-center justify-between gap-3">
                  <span>
                    {a.role_title} · {a.duration_min} min{a.due_date ? ` · due ${fmtDate(a.due_date)}` : ''}
                  </span>
                  <span className={`chip shrink-0 whitespace-nowrap ${a.status === 'overdue' ? 'bg-red-100 text-red-800' : a.status === 'done' ? 'bg-emerald-100 text-emerald-800' : 'bg-slate-100 text-slate-700'}`}>
                    {STATUS_LABELS[a.status]}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      <div className="card p-6">
        <h2 className="text-lg font-bold">Reports</h2>
        <ul className="mt-3 divide-y divide-line-soft">
          {c.sessions.map((x) => (
            <li key={x.session_id}>
              <Link
                to={`/coach/${orgId}/candidates/${candidateId}/report/${x.session_id}`}
                className="flex items-center justify-between gap-3 py-3 hover:bg-surface"
              >
                <span>
                  <span className="font-semibold">{x.role_title}</span>
                  <span className="block text-xs text-slate-500">
                    {fmtDate(x.date)} · {x.duration_min} min
                    {x.comments ? ` · ${x.comments} comment${x.comments === 1 ? '' : 's'}` : ''}
                  </span>
                </span>
                <span className="text-lg font-bold tabular-nums">{fmt(x.overall_score)}</span>
              </Link>
            </li>
          ))}
        </ul>
      </div>
    </section>
  )
}
