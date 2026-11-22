import { Link } from 'react-router-dom'
import { useAuth } from '../lib/auth'
import { Logo } from './Layout'
import InstallApp from './InstallApp'
import ThemeToggle from './ThemeToggle'

// Header for pages anyone can open without an account (decoder, shared reports).
export default function PublicShell({ children }) {
  const { user } = useAuth()
  return (
    <div className="min-h-screen">
      <header className="border-b border-line bg-cream/85 pt-[env(safe-area-inset-top)] backdrop-blur-md print:hidden">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center gap-x-4 gap-y-3 px-4 py-3">
          <Link to="/">
            <Logo compact />
          </Link>
          <nav className="ml-auto flex flex-wrap items-center gap-3 text-sm">
            <InstallApp />
            <ThemeToggle />
            {user ? (
              <Link to="/" className="btn-secondary">
                Go to my dashboard
              </Link>
            ) : (
              <>
                <Link to="/login" className="btn-link">
                  Log in
                </Link>
                <Link to="/signup" className="btn-primary px-4 py-2 text-sm">
                  Sign up free
                </Link>
              </>
            )}
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-4 pt-8 pb-[calc(2rem+env(safe-area-inset-bottom))] sm:pt-10">{children}</main>
    </div>
  )
}
