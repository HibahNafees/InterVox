import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { brandStyle } from '../lib/orgs'

// Accept a coach's invite link, then choose separately whether to share reports (T-166).
export default function Join() {
  const { token } = useParams()
  const { user } = useAuth()
  const [org, setOrg] = useState(null)
  const [joined, setJoined] = useState(false)
  const [share, setShare] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    api(`/orgs/invites/${token}`)
      .then((data) => {
        setOrg(data.org)
        setJoined(data.member)
      })
      .catch(() => setError('This invite link is invalid or has expired.'))
  }, [token])

  async function join() {
    setError('')
    try {
      const data = await api(`/orgs/invites/${token}/accept`, { method: 'POST' })
      setJoined(true)
      setShare(data.consent)
    } catch (err) {
      setError(err.message)
    }
  }

  async function saveConsent() {
    setError('')
    try {
      await api(`/orgs/${org.id}/consent`, { method: 'PUT', body: { share } })
      setSaved(true)
    } catch (err) {
      setError(err.message)
    }
  }

  if (error && !org) {
    return (
      <p role="alert" className="text-red-600">
        {error}
      </p>
    )
  }
  if (!org) return <p className="animate-pulse text-slate-500">Loading the invite…</p>

  return (
    <section className="mx-auto max-w-lg space-y-6" style={brandStyle(org)}>
      <div className="card space-y-4 p-6 text-center">
        {org.logo && <img src={org.logo} alt={`${org.name} logo`} className="mx-auto h-16 w-16 rounded-2xl" />}
        <h1 className="text-2xl font-extrabold">{org.name}</h1>
        {!joined ? (
          <>
            <p className="text-slate-600">
              {org.name} invited you, {user.name}, to practise interviews with their coaches.
            </p>
            <button className="rounded-full px-6 py-3 font-semibold text-white" style={{ background: 'var(--org)' }} onClick={join}>
              Join {org.name}
            </button>
          </>
        ) : (
          <div className="space-y-4 text-left">
            <p className="text-slate-600">You’re in. Your coach can assign you interviews.</p>
            <label className="flex items-start gap-3 rounded-2xl p-4 ring-1 ring-line">
              <input type="checkbox" className="mt-1" checked={share} onChange={(e) => setShare(e.target.checked)} />
              <span>
                <span className="font-semibold">Share my interview reports with {org.name}’s coaches</span>
                <span className="block text-sm text-slate-500">
                  They’ll see your scores, answers and progress so they can coach you. You can stop sharing
                  any time on your Account page.
                </span>
              </span>
            </label>
            <div className="flex items-center gap-3">
              <button className="btn-primary" onClick={saveConsent}>
                Save
              </button>
              {saved && <span className="text-sm text-emerald-700">Saved</span>}
              <Link to="/" className="btn-link ml-auto">
                Go to my dashboard
              </Link>
            </div>
          </div>
        )}
        {error && (
          <p role="alert" className="text-sm text-red-600">
            {error}
          </p>
        )}
      </div>
    </section>
  )
}
