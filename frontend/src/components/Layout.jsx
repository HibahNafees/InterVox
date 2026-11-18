import { Link, NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '../lib/auth'
import { Mascot } from './Art'
import ThemeToggle from './ThemeToggle'

const NAV = [
  ['/', 'Dashboard'],
  ['/setup', 'New interview'],
  ['/stories', 'Story bank'],
  ['/decoder', 'JD decoder'],
  ['/debrief', 'Debrief'],
  ['/reverse', 'Reverse'],
  ['/lab', 'Chat Lab'],
]

// `onColor` is for coloured backgrounds (the sign-in panel), where the coral
// "Vox" would disappear.
export function Logo({ onColor = false }) {
  return (
    <span className="flex items-center gap-2">
      <Mascot className="h-10 w-10" />
      <span className="flex flex-col leading-tight">
        <span className={`font-display text-xl font-extrabold tracking-tight ${onColor ? 'text-white' : 'text-ink'}`}>
          Inter
          <span className={onColor ? 'text-night' : 'text-brand-500'}>Vox</span>
        </span>
        <span className={`text-xs font-medium ${onColor ? 'text-white/90' : 'text-ink/70'}`}>
          AI voice practice interviews for any job
        </span>
      </span>
    </span>
  )
}

export default function Layout() {
  const { user, logout } = useAuth()
  return (
    <div className="min-h-screen text-slate-800">
      <header className="sticky top-0 z-10 border-b border-line bg-cream/85 backdrop-blur-md print:hidden">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center gap-x-4 gap-y-3 px-4 py-3">
          <Link to="/" aria-label="InterVox home">
            <Logo />
          </Link>
          <nav className="flex flex-wrap gap-0.5 text-sm">
            {[...NAV, ...(user?.is_admin ? [['/admin', 'Admin']] : [])].map(([to, label]) => (
              <NavLink
                key={to}
                to={to}
                end={to === '/'}
                className={({ isActive }) =>
                  `rounded-full px-2.5 py-1.5 font-medium transition ${
                    isActive ? 'bg-brand-100 text-brand-700' : 'text-slate-600 hover:bg-surface hover:text-slate-900'
                  }`
                }
              >
                {label}
              </NavLink>
            ))}
          </nav>
          {user && (
            <div className="ml-auto flex items-center gap-2 text-sm">
              <ThemeToggle />
              <Link
                to="/account"
                className="flex items-center gap-2 text-slate-700 hover:text-slate-900"
                title={`${user.name}: account and privacy`}
              >
                <span
                  aria-hidden="true"
                  className="grid h-8 w-8 place-items-center rounded-full bg-night text-xs font-bold text-white"
                >
                  {user.name?.[0]?.toUpperCase()}
                </span>
                <span className="sr-only">{user.name}</span>
              </Link>
              <button onClick={() => logout()} className="btn-link">
                Log out
              </button>
            </div>
          )}
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-4 py-8 sm:py-10">
        <Outlet />
      </main>
    </div>
  )
}
