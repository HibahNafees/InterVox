import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'

// The sales demo's View as buttons (T-166). Admin-only: the backend answers 404
// to anyone else, and this renders nothing then.
export default function DemoPanel({ intro = null }) {
  const { viewAsDemo } = useAuth()
  const navigate = useNavigate()
  const [demo, setDemo] = useState(null)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    api('/demo')
      .then((data) => setDemo(data.demo))
      .catch(() => setDemo(null))
  }, [])

  if (!demo) return null

  async function open(kind, to) {
    setError('')
    setBusy(kind)
    try {
      await viewAsDemo(kind)
      navigate(to)
    } catch (err) {
      setError(err.message)
      setBusy('')
    }
  }

  return (
    <div className="card space-y-4 p-6" style={{ borderColor: demo.color }}>
      <div className="flex items-center gap-3">
        <img src={demo.logo} alt="" className="h-10 w-10 rounded-xl" />
        <div>
          <p className="flex items-center gap-2 text-lg font-bold">
            {demo.org} <span className="chip bg-amber-100 text-amber-800">Demo</span>
          </p>
          <p className="text-sm text-slate-600">
            Coach {demo.coach} · {demo.candidates.length} fictional candidates
          </p>
        </div>
      </div>
      {intro}
      {!demo.seeded && (
        <p role="alert" className="text-sm text-red-600">
          The demo isn’t set up yet. Run <code>flask demo-reset</code> on the server.
        </p>
      )}
      <div className="flex flex-wrap gap-3">
        <button className="btn-primary" disabled={!demo.seeded || !!busy} onClick={() => open('coach', '/coach')}>
          {busy === 'coach' ? 'Opening…' : 'View as demo coach'}
        </button>
        <button className="btn-secondary" disabled={!demo.seeded || !!busy} onClick={() => open('candidate', '/')}>
          {busy === 'candidate' ? 'Opening…' : 'View as demo candidate'}
        </button>
        <button className="btn-secondary" disabled={!demo.seeded || !!busy} onClick={() => open('struggling', '/')}>
          {busy === 'struggling' ? 'Opening…' : 'View as struggling candidate'}
        </button>
      </div>
      {error && (
        <p role="alert" className="text-sm text-red-600">
          {error}
        </p>
      )}
      <p className="text-xs text-slate-500">
        Everything in the demo is made up, makes no AI calls, and resets every night.
      </p>
    </div>
  )
}
