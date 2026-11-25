import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useDialogs } from '../components/ConfirmDialog'
import { api } from '../lib/api'
import { brandStyle } from '../lib/orgs'
import { OrgHeader } from './Coach'

const MAX_LOGO_BYTES = 100 * 1024

// Org branding and members, for the org's admin (T-166).
export default function OrgSettings() {
  const { orgId } = useParams()
  const { notify } = useDialogs()
  const [org, setOrg] = useState(null)
  const [members, setMembers] = useState([])
  const [form, setForm] = useState({ name: '', color: '#1f6f8b', logo: null })
  const [error, setError] = useState('')

  useEffect(() => {
    api(`/orgs/${orgId}`)
      .then(({ org }) => {
        setOrg(org)
        setForm({ name: org.name, color: org.color || '#1f6f8b', logo: org.logo })
      })
      .catch((err) => setError(err.message))
    api(`/orgs/${orgId}/members`)
      .then((data) => setMembers(data.members))
      .catch(() => {})
  }, [orgId])

  function pickLogo(file) {
    if (!file) return
    if (file.size > MAX_LOGO_BYTES) {
      setError('The logo must be under 100 KB.')
      return
    }
    const reader = new FileReader()
    reader.onload = () => setForm((f) => ({ ...f, logo: reader.result }))
    reader.readAsDataURL(file)
  }

  async function save(e) {
    e.preventDefault()
    setError('')
    try {
      const data = await api(`/orgs/${orgId}`, {
        method: 'PUT',
        body: { name: form.name, color: form.color, logo: form.logo ?? '' },
      })
      setOrg(data.org)
      notify('Branding saved')
    } catch (err) {
      setError(err.message)
    }
  }

  if (!org) {
    return error ? (
      <p role="alert" className="text-red-600">
        {error}
      </p>
    ) : (
      <p className="animate-pulse text-slate-500">Loading…</p>
    )
  }
  const preview = { ...org, name: form.name || org.name, color: form.color, logo: form.logo }

  return (
    <section className="space-y-6" style={brandStyle(preview)}>
      <Link to="/coach" className="btn-link">
        ← Candidates
      </Link>
      <OrgHeader org={preview} title="Branding and members" />
      <form onSubmit={save} className="card space-y-4 p-6">
        <label className="block space-y-1 text-sm font-medium">
          <span>Organization name</span>
          <input className="field" required maxLength={120} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        </label>
        <label className="flex items-center gap-3 text-sm font-medium">
          <span>Primary color</span>
          <input type="color" value={form.color} onChange={(e) => setForm({ ...form, color: e.target.value })} />
          <code>{form.color}</code>
        </label>
        <div className="space-y-1 text-sm font-medium">
          <span>Logo (PNG, JPEG, WebP or SVG, under 100 KB)</span>
          <div className="flex items-center gap-3">
            <input type="file" accept="image/png,image/jpeg,image/webp,image/svg+xml" aria-label="Logo" onChange={(e) => pickLogo(e.target.files[0])} />
            {form.logo && (
              <button type="button" className="btn-link" onClick={() => setForm({ ...form, logo: null })}>
                Remove logo
              </button>
            )}
          </div>
        </div>
        {error && (
          <p role="alert" className="text-sm text-red-600">
            {error}
          </p>
        )}
        <button className="btn-primary">Save branding</button>
      </form>
      <div className="card p-6">
        <h2 className="text-lg font-bold">Members</h2>
        <ul className="mt-3 divide-y divide-line-soft text-sm">
          {members.map((m) => (
            <li key={m.id} className="flex items-center justify-between py-2">
              <span>{m.name}</span>
              <span className="text-slate-500">
                {m.role}
                {m.role === 'candidate' && (m.consent ? ' · sharing reports' : ' · not sharing')}
              </span>
            </li>
          ))}
        </ul>
      </div>
    </section>
  )
}
