// Coach comments on a report (T-166).
export default function CommentList({ comments }) {
  if (!comments.length) return <p className="text-sm text-slate-500">No comments yet.</p>
  return (
    <ul className="space-y-3">
      {comments.map((c) => (
        <li key={c.id} className="rounded-2xl bg-surface p-4 ring-1 ring-line">
          <p className="text-xs font-semibold text-slate-500">
            {c.author} · {new Date(c.created_at).toLocaleDateString()}
          </p>
          <p className="mt-1 whitespace-pre-line text-slate-800">{c.body}</p>
        </li>
      ))}
    </ul>
  )
}
