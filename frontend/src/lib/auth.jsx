import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { api, getToken, setToken } from './api'

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
      .catch(() => setToken(null))
      .finally(() => setLoading(false))
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
    setUser(null)
    setNotice(typeof message === 'string' ? message : '')
  }, [])

  return (
    <AuthContext.Provider value={{ user, loading, login, signup, googleLogin, logout, notice }}>
      {children}
    </AuthContext.Provider>
  )
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth() {
  return useContext(AuthContext)
}
