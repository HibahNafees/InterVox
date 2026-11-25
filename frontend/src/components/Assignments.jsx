import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { STATUS_LABELS, brandStyle, candidateOrgs, fmtDate } from '../lib/orgs'
import { useDialogs } from './ConfirmDialog'

const TONES = {
  todo: 'bg-slate-100 text-slate-700',
  in_progress: 'bg-amber-100 text-amber-800',
  done: 'bg-emerald-100 text-emerald-800',
  overdue: 'bg-red-100 text-red-800',
}

// Interviews the candidate's coach assigned (T-166). Only for org members.
export default function Assignments() {
  const { user } = useAuth()
  const { notify } = useDialogs()
  const navigate = useNavigate()
  const org = candidateOrgs(user)[0]
  const [items, setItems] = useState(null)

  useEffect(() => {
    if (!org) return
    api('/orgs/mine')
      .then((data) => setItems(data.assignments))
      .catch(() => setItems([]))
  }, [org])

  if (!org || !items?.length) return null

  function start(a) {
    if (user.is_demo) {
      notify('This is the demo: live interviews are off.')
      return
    }
    navigate(`/setup?assignment=${a.id}`)
  }

  return (
    <div className="card space-y-4 p-6" style={brandStyle(org)}>
      <div className="flex items-center gap-3">
        {org.logo && <img src={org.logo} alt="" className="h-9 w-9 rounded-xl" />}
        <div>
          <h2 className="text-lg font-bold">Assigned by your coach</h2>
          <p className="text-sm text-slate-500">{org.name}</p>
        </div>
      </div>
      <ul className="divide-y divide-line-soft">
        {items.map((a) => (
          <li key={a.id} className="flex flex-wrap items-center gap-3 py-3">
            <div className="min-w-0 flex-1">
              <p className="font-semibold">{a.role_title}</p>
              <p className="text-xs text-slate-500">
                {a.duration_min} min{a.due_date ? ` · due ${fmtDate(a.due_date)}` : ''}
                {a.coach_name ? ` · from ${a.coach_name}` : ''}
              </p>
            </div>
            <span className={`chip ${TONES[a.status]}`}>{STATUS_LABELS[a.status]}</span>
            {a.status === 'done' && a.session_id ? (
              <Link to={`/report/${a.session_id}`} className="btn-secondary">
                See report
              </Link>
            ) : a.status === 'in_progress' && a.session_id ? (
              <Link to={`/interview/${a.session_id}`} className="btn-secondary">
                Continue
              </Link>
            ) : (
              <button className="rounded-full px-4 py-2 text-sm font-semibold text-white" style={{ background: 'var(--org)' }} onClick={() => start(a)}>
                Start
              </button>
            )}
          </li>
        ))}
      </ul>
    </div>
  )
}
