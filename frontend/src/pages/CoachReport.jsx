import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { brandStyle, staffOrg } from '../lib/orgs'
import CommentList from '../components/CommentList'
import { ReportView } from './Report'

// A candidate's report as their coach sees it: read-only, plus comments (T-166).
export default function CoachReport() {
  const { orgId, candidateId, sessionId } = useParams()
  const { user } = useAuth()
  const org = staffOrg(user)
  const base = `/orgs/${orgId}/candidates/${candidateId}/sessions/${sessionId}`
  const [report, setReport] = useState(null)
  const [comments, setComments] = useState([])
  const [text, setText] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api(`${base}/report`)
      .then((data) => setReport(data.report))
      .catch((err) => setError(err.message))
    api(`${base}/comments`)
      .then((data) => setComments(data.comments))
      .catch(() => {})
  }, [base])

  async function send(e) {
    e.preventDefault()
    setBusy(true)
    try {
      const { comment } = await api(`${base}/comments`, { method: 'POST', body: { body: text } })
      setComments((c) => [...c, comment])
      setText('')
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  if (!report) {
    return error ? (
      <p role="alert" className="text-red-600">
        {error}
      </p>
    ) : (
      <p className="animate-pulse text-slate-500">Loading the report…</p>
    )
  }

  return (
    <div className="space-y-6" style={brandStyle(org)}>
      <Link to={`/coach/${orgId}/candidates/${candidateId}`} className="btn-link">
        ← Back to the candidate
      </Link>
      <section className="card space-y-4 p-6" aria-labelledby="coach-comments">
        <h2 id="coach-comments" className="text-lg font-bold">
          Your comments
        </h2>
        <CommentList comments={comments} />
        <form onSubmit={send} className="space-y-2">
          <label htmlFor="comment" className="sr-only">
            Add a comment
          </label>
          <textarea
            id="comment"
            className="field min-h-24"
            maxLength={2000}
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="What should they focus on next?"
          />
          {error && (
            <p role="alert" className="text-sm text-red-600">
              {error}
            </p>
          )}
          <button className="btn-primary" disabled={busy || !text.trim()}>
            {busy ? 'Sending…' : 'Add comment'}
          </button>
        </form>
        <p className="text-xs text-slate-500">The candidate sees your comments on their report.</p>
      </section>
      <ReportView report={report} shared title="Candidate report" />
    </div>
  )
}
