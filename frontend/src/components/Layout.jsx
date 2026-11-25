import { useEffect, useState } from 'react'
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../lib/auth'
import { staffOrg } from '../lib/orgs'
import { Mascot } from './Art'
import InstallApp from './InstallApp'
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
export function Logo({ onColor = false, compact = false }) {
  return (
    <span className="flex items-center gap-2">
      <Mascot className="h-10 w-10" />
      <span className="flex flex-col leading-tight">
        <span className={`font-display text-xl font-extrabold tracking-tight ${onColor ? 'text-white' : 'text-ink'}`}>
          Inter
          <span className={onColor ? 'text-night' : 'text-brand-500'}>Vox</span>
        </span>
        <span className={`text-xs font-medium ${compact ? 'hidden sm:block' : ''} ${onColor ? 'text-white/90' : 'text-ink/70'}`}>
          AI voice practice interviews for any job
        </span>
      </span>
    </span>
  )
}

// Shown while an admin views a demo account (T-166).
function DemoBar({ user, onBack }) {
  return (
    <div className="bg-amber-100 text-amber-900 print:hidden">
      <div className="mx-auto flex max-w-5xl flex-wrap items-center gap-x-3 gap-y-1 px-4 py-2 text-sm">
        <span className="chip bg-amber-300 text-amber-950">Demo</span>
        <span>
          Viewing as the demo {user.demo_role}, <strong>{user.name}</strong>. Fictional data; AI features are off.
        </span>
        <button onClick={onBack} className="ml-auto font-semibold underline underline-offset-4">
          Back to admin
        </button>
      </div>
    </div>
  )
}

export default function Layout() {
  const { user, logout, backToAdmin } = useAuth()
  const navigate = useNavigate()
  const coachOrg = staffOrg(user)
  const nav = [
    ...(coachOrg ? [['/coach', 'Coach']] : []),
    ...NAV,
    ...(user?.is_admin ? [['/admin', 'Admin']] : []),
    ...(user?.can_use_demo ? [['/demo', 'Demo']] : []),
  ]
  async function back() {
    await backToAdmin()
    navigate('/admin')
  }
  const [menuOpen, setMenuOpen] = useState(false)
  const { pathname } = useLocation()
  // Phones: the nav folds behind a Menu button and closes after each move (T-150).
  useEffect(() => setMenuOpen(false), [pathname])
  return (
    <div className="min-h-screen text-slate-800">
      {user?.is_demo && <DemoBar user={user} onBack={back} />}
      <header className="sticky top-0 z-10 border-b border-line bg-cream/85 pt-[env(safe-area-inset-top)] backdrop-blur-md print:hidden">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center gap-x-4 gap-y-3 px-4 py-3">
          <Link to="/" aria-label="InterVox home">
            <Logo compact />
          </Link>
          <nav
            id="main-nav"
            aria-label="Main"
            className={`${menuOpen ? 'flex' : 'hidden'} order-last w-full flex-col gap-0.5 text-sm sm:order-none sm:flex sm:w-auto sm:flex-row sm:flex-wrap`}
          >
            {nav.map(([to, label]) => (
              <NavLink
                key={to}
                to={to}
                end={to === '/'}
                className={({ isActive }) =>
                  `rounded-full px-3 py-2.5 font-medium transition sm:px-2.5 sm:py-1.5 ${
                    isActive ? 'bg-brand-100 text-brand-700' : 'text-slate-600 hover:bg-surface hover:text-slate-900'
                  }`
                }
              >
                {label}
              </NavLink>
            ))}
            {user && (
              <span className="flex items-center justify-between gap-2 border-t border-line px-3 pt-3 sm:hidden">
                <InstallApp />
                <button onClick={() => (user.is_demo ? back() : logout())} className="btn-link ml-auto">
                  Log out
                </button>
              </span>
            )}
          </nav>
          {user && (
            <div className="ml-auto flex items-center gap-2 text-sm">
              <span className="hidden sm:flex">
                <InstallApp />
              </span>
              <ThemeToggle />
              <Link
                to="/account"
                className="flex items-center gap-2 text-slate-700 hover:text-slate-900"
                title={`${user.name}: account and privacy`}
              >
                <span
                  aria-hidden="true"
                  className="grid h-9 w-9 place-items-center rounded-full bg-night text-xs font-bold text-white"
                >
                  {user.name?.[0]?.toUpperCase()}
                </span>
                <span className="sr-only">{user.name}</span>
              </Link>
              <button onClick={() => (user.is_demo ? back() : logout())} className="btn-link hidden sm:inline">
                Log out
              </button>
              <button
                type="button"
                onClick={() => setMenuOpen((o) => !o)}
                aria-expanded={menuOpen}
                aria-controls="main-nav"
                className="grid h-9 min-w-9 place-items-center rounded-full px-3 font-medium ring-1 ring-line hover:bg-surface sm:hidden"
              >
                {menuOpen ? 'Close' : 'Menu'}
              </button>
            </div>
          )}
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-4 pt-8 pb-[calc(2rem+env(safe-area-inset-bottom))] sm:pt-10 sm:pb-[calc(2.5rem+env(safe-area-inset-bottom))]">
        <Outlet />
      </main>
    </div>
  )
}
