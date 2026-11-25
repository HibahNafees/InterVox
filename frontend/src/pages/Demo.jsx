import DemoPanel from '../components/DemoPanel'
import NotFound from '../components/NotFound'
import { useAuth } from '../lib/auth'

// The agency pitch page (T-166). Admin-only for now; the backend 404s everyone else.
export default function Demo() {
  const { user } = useAuth()
  if (!user?.can_use_demo) return <NotFound />
  return (
    <section className="space-y-6">
      <header>
        <p className="eyebrow">For career agencies</p>
        <h1 className="mt-1 text-3xl font-extrabold text-slate-900">InterVox for coaches</h1>
      </header>
      <div className="card space-y-3 p-6 text-slate-700">
        <p>
          Your candidates practise real interviews for any job, out loud, and get a scored report with
          a stronger version of every answer.
        </p>
        <ul className="list-disc space-y-1 pl-5">
          <li>See every candidate’s latest score, trend and weak areas on one dashboard.</li>
          <li>Spot who needs practice, assign an interview with a due date, and comment on reports.</li>
          <li>Candidates choose to share their reports; each agency’s data stays separate.</li>
          <li>Your logo and colour on your agency’s pages.</li>
        </ul>
      </div>
      <DemoPanel />
    </section>
  )
}
