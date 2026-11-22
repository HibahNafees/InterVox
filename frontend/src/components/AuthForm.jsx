import { useState } from 'react'
import { HeroScene } from './Art'
import GoogleSignIn from './GoogleSignIn'
import { Logo } from './Layout'
import ThemeToggle from './ThemeToggle'

export default function AuthForm({ title, fields, submitLabel, onSubmit, footer, notice }) {
  const [values, setValues] = useState(() => Object.fromEntries(fields.map((f) => [f.name, ''])))
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function handleSubmit(e) {
    e.preventDefault()
    setError('')
    setBusy(true)
    try {
      await onSubmit(values)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="grid min-h-screen lg:grid-cols-2">
      <aside className="relative hidden flex-col justify-between overflow-hidden bg-gradient-to-br from-brand-400 via-brand-500 to-accent-400 p-12 text-white lg:flex">
        <Logo onColor />
        <div>
          <h2 className="font-display text-4xl leading-tight font-extrabold text-white">
            AI practice interviews that tell you exactly what to fix.
          </h2>
          <ul className="mt-6 space-y-2 text-white/90">
            <li>🎙️ Answer out loud, like the real thing</li>
            <li>📊 Scores on what this job looks for</li>
            <li>✨ A stronger version of every answer</li>
          </ul>
        </div>
        <HeroScene className="h-64" />
      </aside>
      <div className="relative flex flex-col items-center justify-center gap-6 px-4 py-10">
        <ThemeToggle className="absolute top-4 right-4" />
        <div className="flex justify-center lg:hidden">
          <Logo />
        </div>
      <form onSubmit={handleSubmit} className="card w-full max-w-sm space-y-4 p-8">
        <h1 className="text-3xl font-extrabold">{title}</h1>
        {notice && (
          <p role="status" className="rounded-lg bg-green-50 p-3 text-sm text-green-800">
            {notice}
          </p>
        )}
        <GoogleSignIn onError={setError} />
        {fields.map((f) => (
          <label key={f.name} className="block text-sm">
            <span className="font-medium text-slate-700">{f.label}</span>
            <input
              type={f.type}
              name={f.name}
              autoComplete={f.autoComplete}
              required
              minLength={f.minLength}
              value={values[f.name]}
              onChange={(e) => setValues((v) => ({ ...v, [f.name]: e.target.value }))}
              className="field mt-1.5"
            />
          </label>
        ))}
        {error && (
          <p role="alert" className="text-sm text-red-600">
            {error}
          </p>
        )}
        <button
          type="submit"
          disabled={busy}
          className="btn-primary w-full"
        >
          {busy ? 'Please wait…' : submitLabel}
        </button>
        <p className="text-center text-sm text-slate-600">{footer}</p>
      </form>
      </div>
    </div>
  )
}
