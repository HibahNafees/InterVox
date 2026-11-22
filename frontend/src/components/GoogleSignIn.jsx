import { useEffect, useRef, useState } from 'react'
import { useAuth } from '../lib/auth'
import { googleClientId, loadGoogleScript, nativeGoogleToken } from '../lib/google'
import { isNativeApp } from '../lib/native'
import { useTheme } from '../lib/theme'

// "Continue with Google" above the email form (T-156); hidden when the API has no
// Google client id. New users get an account, returning ones are logged in.
export default function GoogleSignIn({ onError }) {
  const { googleLogin } = useAuth()
  const [clientId, setClientId] = useState(null)
  const [busy, setBusy] = useState(false)
  const native = isNativeApp()
  const theme = useTheme()
  const box = useRef(null)

  useEffect(() => {
    let live = true
    googleClientId().then((id) => live && setClientId(id))
    return () => {
      live = false
    }
  }, [])

  // Website: Google draws its own button (its branding rules require it).
  useEffect(() => {
    if (!clientId || native) return
    let live = true
    loadGoogleScript()
      .then((google) => {
        if (!live || !box.current) return
        google.accounts.id.initialize({
          client_id: clientId,
          callback: async ({ credential }) => {
            onError('')
            try {
              await googleLogin(credential)
            } catch (err) {
              onError(err.message)
            }
          },
          ux_mode: 'popup',
          use_fedcm_for_button: true,
        })
        box.current.replaceChildren()
        google.accounts.id.renderButton(box.current, {
          type: 'standard',
          theme: theme === 'dark' ? 'filled_black' : 'outline',
          size: 'large',
          shape: 'pill',
          text: 'continue_with',
          logo_alignment: 'center',
          width: Math.min(box.current.offsetWidth || 320, 400),
        })
      })
      .catch((err) => live && onError(err.message))
    return () => {
      live = false
    }
  }, [clientId, native, theme, googleLogin, onError])

  async function nativeSignIn() {
    onError('')
    setBusy(true)
    try {
      const token = await nativeGoogleToken(clientId)
      if (token) await googleLogin(token)
    } catch (err) {
      onError(err.message)
    } finally {
      setBusy(false)
    }
  }

  if (!clientId) return null
  return (
    <div className="space-y-4">
      {native ? (
        <button type="button" onClick={nativeSignIn} disabled={busy} className="btn-secondary flex w-full items-center justify-center gap-2">
          <GoogleG />
          {busy ? 'Please wait…' : 'Continue with Google'}
        </button>
      ) : (
        <div ref={box} data-testid="google-button" className="flex min-h-10 justify-center" />
      )}
      <p className="flex items-center gap-3 text-xs font-medium tracking-wide text-slate-500 uppercase">
        <span className="h-px flex-1 bg-line" />
        or with email
        <span className="h-px flex-1 bg-line" />
      </p>
    </div>
  )
}

// Google's "G" mark, as Google's sign-in branding guidelines ask for.
function GoogleG() {
  return (
    <svg aria-hidden="true" viewBox="0 0 48 48" className="h-5 w-5">
      <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z" />
      <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z" />
      <path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z" />
      <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z" />
    </svg>
  )
}
