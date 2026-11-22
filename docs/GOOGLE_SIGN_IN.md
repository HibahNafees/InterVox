# Sign in with Google (T-156)

People can sign up and log in with their Google account instead of a name, email and
password. It is free (Google Identity Services) and needs no Google secret: the
OAuth client id is public, and Flask checks every Google ID token's signature,
audience (`GOOGLE_CLIENT_IDS`), issuer and `email_verified` with `google-auth`.

- **Website:** Google's own "Continue with Google" button (`components/GoogleSignIn.jsx`,
  `lib/google.js`) → ID token → `POST /api/auth/google`.
- **Android app:** Google blocks sign-in inside WebViews, so the app uses the native
  account picker (Credential Manager via `@capgo/capacitor-social-login`) and sends the
  same kind of ID token to the same endpoint.
- **Accounts:** a new Google user gets an account with no password (`users.google_sub`
  set, `password_hash` NULL). If an account with the same verified email exists, the
  Google sign-in logs into it and links it; its password keeps working.
- **Delete my data:** a Google-only account confirms by typing its email.
- **Off switch:** with `GOOGLE_CLIENT_IDS` empty, `GET /api/auth/providers` returns no
  id and the button is hidden everywhere.

## One-time setup in Google Cloud Console (free)

1. https://console.cloud.google.com → create a project, e.g. **InterVox**.
2. **Google Auth Platform → Branding:** app name *InterVox*, your support email,
   app domain `https://www.intervox.site`, authorised domain `intervox.site`.
   **Audience:** *External*, then **Publish app** (status *In production*). With only the
   basic scopes (openid, email, profile) Google needs no app review.
3. **Clients → Create client → Web application**, name *InterVox web*.
   Authorised JavaScript origins:
   - `https://www.intervox.site`
   - `https://intervox.site`
   - `https://intervox-pi.vercel.app`
   - `http://localhost:5173` (local dev)

   No redirect URIs (the button uses a popup). Copy the **Client ID**
   (`…apps.googleusercontent.com`). It is public, not a secret.
4. **Clients → Create client → Android**, name *InterVox Android*:
   package `site.intervox.app`, SHA-1 of the release keystore (on the Mac):
   ```bash
   keytool -list -v -keystore ~/.intervox/intervox-release.jks -alias intervox | grep SHA1
   ```
   Nothing from this client goes in the code; Google uses it to trust the app. The app
   signs in with the **Web** client id. (A debug build has a different SHA-1; add a
   second Android client for it if you test debug builds.)
5. The Web client id goes into the server's `.env` as `GOOGLE_CLIENT_IDS=<id>` (through
   a master deploy) and into the vault (`ai_providers` slug `google-oauth`).

## Checking it

- `curl https://intervox.duckdns.org/api/auth/providers` → `{"google_client_id": "…"}`.
- Website: the button appears on /login and /signup; picking an account lands on the
  dashboard.
- App: after `npm run build:android` and a new signed APK, "Continue with Google" opens
  the system account sheet. `Developer console is not set up correctly` (Logcat tag
  `GoogleProvider`) means the Android client's package or SHA-1 doesn't match.
