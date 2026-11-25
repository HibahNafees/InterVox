import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { api, getAdminToken, getToken, setAdminToken, setToken } from './api'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  // A one-line message for the login page (e.g. after deleting the account).
  const [notice, setNotice] = useState('')
  const [loading, setLoading] = useState(() => Boolean(getToken()))

  useEffect(() => {
    if (!getToken()) return
    api('/auth/me')
      .then((data) => setUser(data.user))
      .catch(async () => {
        setToken(null)
        // A demo view that expired (2 hours): back to the admin's own session.
        const admin = getAdminToken()
        setAdminToken(null)
        if (!admin) return
        setToken(admin)
        try {
          setUser((await api('/auth/me')).user)
        } catch {
          setToken(null)
        }
      })
      .finally(() => setLoading(false))
  }, [])

  // Admin only (T-166): open a demo account in this tab, keeping the admin's
  // own token aside for Back to admin.
  const viewAsDemo = useCallback(async (kind) => {
    const data = await api('/demo/view-as', { method: 'POST', body: { view_as: kind } })
    if (!getAdminToken()) setAdminToken(getToken())
    setToken(data.access_token)
    setUser((await api('/auth/me')).user)
  }, [])

  const backToAdmin = useCallback(async () => {
    const admin = getAdminToken()
    setAdminToken(null)
    setToken(admin)
    // Swap users in one step: clearing first would bounce to the login page.
    try {
      setUser(admin ? (await api('/auth/me')).user : null)
    } catch {
      setToken(null)
      setUser(null)
    }
  }, [])

  const handleAuth = useCallback((data) => {
    setToken(data.access_token)
    setUser(data.user)
    setNotice('')
  }, [])

  const login = useCallback(
    async (email, password) =>
      handleAuth(await api('/auth/login', { method: 'POST', body: { email, password } })),
    [handleAuth],
  )

  const signup = useCallback(
    async (name, email, password) =>
      handleAuth(
        await api('/auth/signup', { method: 'POST', body: { name, email, password } }),
      ),
    [handleAuth],
  )

  // Sign in with Google (T-156): a Google ID token for an InterVox session.
  const googleLogin = useCallback(
    async (credential) => handleAuth(await api('/auth/google', { method: 'POST', body: { credential } })),
    [handleAuth],
  )

  const logout = useCallback((message = '') => {
    setToken(null)
    setAdminToken(null)
    setUser(null)
    setNotice(typeof message === 'string' ? message : '')
  }, [])

  return (
    <AuthContext.Provider value={{ user, loading, login, signup, googleLogin, logout, notice, viewAsDemo, backToAdmin }}>
      {children}
    </AuthContext.Provider>
  )
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth() {
  return useContext(AuthContext)
}
