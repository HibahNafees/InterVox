import { useEffect, useState } from 'react'
import DemoPanel from '../components/DemoPanel'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'

function usd(n) {
  return `$${n < 0.01 && n > 0 ? n.toFixed(4) : n.toFixed(2)}`
}

export default function Admin() {
  const { user } = useAuth()
  const [usage, setUsage] = useState(null)
  const [error, setError] = useState('')
  useEffect(() => {
    api('/admin/usage')
      .then((data) => setUsage(data.usage))
      .catch((err) => setError(err.message))
  }, [])

  if (error) {
    return (
      <p role="alert" className="text-red-600">
        {error}
      </p>
    )
  }
  if (!usage) return <p className="animate-pulse text-slate-500">Loading usage…</p>

  const pct = Math.round((usage.month_spend_usd / usage.budget_usd) * 100)
  const active = usage.days.filter((d) => d.fire_calls || d.minutes || d.sessions)
  return (
    <section className="space-y-6">
      <header>
        <p className="eyebrow">Admin</p>
        <h1 className="mt-1 text-3xl font-extrabold text-slate-900">Usage and Fire spend</h1>
      </header>

      {user?.can_use_demo && <DemoPanel />}

      <div className="card grid gap-4 p-6 sm:grid-cols-3">
        <div>
          <p className="text-sm text-slate-500">Fire spend this month</p>
          <p className="text-2xl font-extrabold tabular-nums">
            {usd(usage.month_spend_usd)} <span className="text-base font-medium text-slate-500">of {usd(usage.budget_usd)}</span>
          </p>
          <p className="text-sm text-slate-600">{pct}% used · {usd(usage.budget_left_usd)} left</p>
        </div>
        <div>
          <p className="text-sm text-slate-500">New sessions</p>
          <p className={`text-2xl font-extrabold ${usage.paused ? 'text-red-700' : 'text-emerald-700'}`}>
            {usage.paused ? 'Paused (budget used)' : 'Open'}
          </p>
        </div>
        <div>
          <p className="text-sm text-slate-500">Accounts</p>
          <p className="text-2xl font-extrabold tabular-nums">{usage.users_total}</p>
        </div>
      </div>

      <div className="card overflow-x-auto p-6">
        <h2 className="text-lg font-bold">Last 30 days</h2>
        {active.length === 0 ? (
          <p className="mt-2 text-sm text-slate-500">No usage yet.</p>
        ) : (
          <table className="mt-3 w-full text-sm tabular-nums">
            <thead className="text-left text-slate-500">
              <tr>
                <th className="py-1 pr-4 font-medium">Day</th>
                <th className="py-1 pr-4 text-right font-medium">Active users</th>
                <th className="py-1 pr-4 text-right font-medium">Sessions</th>
                <th className="py-1 pr-4 text-right font-medium">Minutes</th>
                <th className="py-1 pr-4 text-right font-medium">Decodes</th>
                <th className="py-1 pr-4 text-right font-medium">Fire calls</th>
                <th className="py-1 text-right font-medium">Spend</th>
              </tr>
            </thead>
            <tbody>
              {active.map((d) => (
                <tr key={d.date} className="border-t border-slate-100">
                  <td className="py-1 pr-4">{d.date}</td>
                  <td className="py-1 pr-4 text-right">{d.users}</td>
                  <td className="py-1 pr-4 text-right">{d.sessions}</td>
                  <td className="py-1 pr-4 text-right">{d.minutes}</td>
                  <td className="py-1 pr-4 text-right">{d.decoder_runs}</td>
                  <td className="py-1 pr-4 text-right">{d.fire_calls}</td>
                  <td className="py-1 text-right">{usd(d.spend_usd)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="card overflow-x-auto p-6">
        <h2 className="text-lg font-bold">Top users this month</h2>
        {usage.top_users.length === 0 ? (
          <p className="mt-2 text-sm text-slate-500">No signed-in usage this month.</p>
        ) : (
          <table className="mt-3 w-full text-sm tabular-nums">
            <thead className="text-left text-slate-500">
              <tr>
                <th className="py-1 pr-4 font-medium">User</th>
                <th className="py-1 pr-4 text-right font-medium">Sessions</th>
                <th className="py-1 pr-4 text-right font-medium">Minutes</th>
                <th className="py-1 text-right font-medium">Spend</th>
              </tr>
            </thead>
            <tbody>
              {usage.top_users.map((u) => (
                <tr key={u.email} className="border-t border-slate-100">
                  <td className="py-1 pr-4">{u.email}</td>
                  <td className="py-1 pr-4 text-right">{u.sessions}</td>
                  <td className="py-1 pr-4 text-right">{u.minutes}</td>
                  <td className="py-1 text-right">{usd(u.spend_usd)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <p className="mt-3 text-xs text-slate-500">Signed-out decoder spend is counted in the daily totals, not here.</p>
      </div>
    </section>
  )
}
