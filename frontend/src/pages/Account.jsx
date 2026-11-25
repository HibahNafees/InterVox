import { useState } from 'react'
import { useDialogs } from '../components/ConfirmDialog'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { candidateOrgs } from '../lib/orgs'

// Which coaching orgs may see this candidate's reports (T-166).
function OrgSharing({ orgs }) {
  const { notify } = useDialogs()
  const [shared, setShared] = useState(() => Object.fromEntries(orgs.map((o) => [o.id, !!o.consent])))

  async function toggle(org, share) {
    try {
      await api(`/orgs/${org.id}/consent`, { method: 'PUT', body: { share } })
      setShared((s) => ({ ...s, [org.id]: share }))
      notify(share ? `Sharing your reports with ${org.name}` : `Stopped sharing with ${org.name}`)
    } catch (err) {
      notify(err.message)
    }
  }

  return (
    <div className="card space-y-3 p-6 text-sm text-slate-700">
      <h2 className="text-lg font-bold text-slate-900">Your coaches</h2>
      {orgs.map((o) => (
        <label key={o.id} className="flex items-start gap-3">
          <input type="checkbox" className="mt-1" checked={shared[o.id]} onChange={(e) => toggle(o, e.target.checked)} />
          <span>
            <span className="font-semibold">Share my interview reports with {o.name}</span>
            <span className="block text-slate-500">
              Their coaches see your scores, answers and progress only while this is on.
            </span>
          </span>
        </label>
      ))}
    </div>
  )
}

export default function Account() {
  const { user, logout } = useAuth()
  const [password, setPassword] = useState('')
  // A Google-only account has no password: it confirms with its email (T-156).
  const googleOnly = user?.has_password === false
  const [sure, setSure] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function remove(e) {
    e.preventDefault()
    setError('')
    setBusy(true)
    try {
      await api('/auth/me', { method: 'DELETE', body: googleOnly ? { email: password } : { password } })
      logout('Your account and all its data were deleted.')
    } catch (err) {
      setError(err.message)
      setBusy(false)
    }
  }

  return (
    <section className="space-y-6">
      <header>
        <p className="eyebrow">Account</p>
        <h1 className="mt-1 text-3xl font-extrabold text-slate-900">{user?.name}</h1>
        <p className="mt-1 text-slate-600">{user?.email}</p>
      </header>

      <div className="card space-y-3 p-6 text-sm text-slate-700">
        <h2 className="text-lg font-bold text-slate-900">Your data</h2>
        <ul className="list-disc space-y-1 pl-5">
          <li>Audio and video are never stored: each answer is transcribed and the recording is discarded.</li>
          <li>Résumés and job descriptions delete themselves after 30 days unless you save them.</li>
          <li>Body-language analysis runs only in your browser; just a few percentages are saved.</li>
          <li>Shared report links can be turned off from the report at any time.</li>
        </ul>
      </div>

      {candidateOrgs(user).length > 0 && <OrgSharing orgs={candidateOrgs(user)} />}

      {user?.is_demo ? (
        <p className="card p-6 text-sm text-slate-600">Demo accounts can’t be changed or deleted.</p>
      ) : (
      <form onSubmit={remove} className="card space-y-4 border border-red-200 p-6">
        <div>
          <h2 className="text-lg font-bold text-red-800">Delete my data</h2>
          <p className="mt-1 text-sm text-slate-600">
            Deletes your account and everything in it: documents, interviews, transcripts,
            reports, stories, debriefs and saved decodes. This can't be undone.
          </p>
        </div>
        <label className="block text-sm">
          <span className="font-medium text-slate-700">{googleOnly ? 'Type your email to confirm' : 'Your password'}</span>
          <input
            type={googleOnly ? 'email' : 'password'}
            autoComplete={googleOnly ? 'off' : 'current-password'}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="mt-1 block w-full max-w-sm rounded-lg border border-slate-300 px-3 py-2"
          />
        </label>
        <label className="flex items-center gap-2 text-sm text-slate-700">
          <input type="checkbox" checked={sure} onChange={(e) => setSure(e.target.checked)} />
          I understand everything will be deleted.
        </label>
        {error && (
          <p role="alert" className="text-sm text-red-600">
            {error}
          </p>
        )}
        <button
          type="submit"
          disabled={!password || !sure || busy}
          className="rounded-full bg-red-600 px-5 py-2 font-semibold text-white disabled:opacity-50"
        >
          {busy ? 'Deleting…' : 'Delete everything'}
        </button>
      </form>
      )}
    </section>
  )
}
