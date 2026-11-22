// Sign in with Google (T-156). The website uses Google Identity Services; the
// Android app uses the native Credential Manager (Google blocks sign-in inside
// WebViews). Both hand Flask a Google ID token to check.
import { api } from './api'

let clientIdPromise

// The OAuth Web client id from the API, or null when Google sign-in is off. Only
// a real id is remembered; "off" or a failed request is asked again next time.
export function googleClientId() {
  clientIdPromise ??= api('/auth/providers')
    .then((data) => data.google_client_id || null)
    .catch(() => null)
    .then((id) => {
      if (!id) clientIdPromise = undefined
      return id
    })
  return clientIdPromise
}

let scriptPromise

export function loadGoogleScript() {
  scriptPromise ??= new Promise((resolve, reject) => {
    if (window.google?.accounts?.id) return resolve(window.google)
    const script = document.createElement('script')
    script.src = 'https://accounts.google.com/gsi/client'
    script.async = true
    script.onload = () => resolve(window.google)
    script.onerror = () => {
      scriptPromise = undefined
      reject(new Error("Couldn't load Google sign-in. Check your connection and try again."))
    }
    document.head.appendChild(script)
  })
  return scriptPromise.then(() => window.google)
}

let nativeReady

// Android app: the system's Google account picker → an ID token (null if cancelled).
export async function nativeGoogleToken(clientId) {
  const { SocialLogin } = await import('@capgo/capacitor-social-login')
  nativeReady ??= SocialLogin.initialize({
    google: { webClientId: clientId, mode: 'online', skipAuthOnlyAuthorizationAfterSignIn: true },
  }).catch((err) => {
    nativeReady = undefined
    throw err
  })
  await nativeReady
  let res
  try {
    // No scopes: the default (openid, email, profile) is all we need, and the stock
    // BridgeActivity rejects an explicit list.
    res = await SocialLogin.login({ provider: 'google', options: {} })
  } catch (err) {
    if (/cancel/i.test(err?.message ?? '')) return null
    throw new Error("Google sign-in didn't work. Please try again.")
  }
  const token = res?.result?.idToken
  if (!token) throw new Error("Google sign-in didn't work. Please try again.")
  return token
}
