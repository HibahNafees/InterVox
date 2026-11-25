# InterVox Android app (Capacitor)

The Android app wraps the same Vite frontend with Capacitor 8 (`frontend/android`,
`frontend/capacitor.config.json`). It ships the built web files inside the APK and
calls the live API at `https://intervox.duckdns.org`. The signed release APK is built by
GitHub Actions (`.github/workflows/android.yml`, T-157); building on a Mac still works as a
fallback. The devbox has no Android SDK. Ticket: T-147.

- **App id:** `site.intervox.app` · **name:** InterVox
- **WebView origin:** `https://app.intervox.site`. The live API must list it in
  `CORS_ORIGINS` (`localhost` origins are refused in production). Nothing is hosted at
  that name; it only labels the app's origin.
- **Permissions:** microphone (answers), camera (opt-in body language), internet.
- **Interviewer voice:** Android WebView has no Web Speech synthesis, so the app asks the
  API for Fire audio of each reply (`VOICE_FIRE_FALLBACK`, T-148), up to
  `DAILY_VOICE_REPLIES` per user per day (T-154); after that, replies are text-only.
- **Google sign-in:** native account picker via `@capgo/capacitor-social-login`
  (T-156). Needs an *Android* OAuth client in Google Cloud with package
  `site.intervox.app` and the release keystore's SHA-1; see `docs/GOOGLE_SIGN_IN.md`.
- **Release certificate SHA-1:** `84:EA:2A:6A:29:65:BB:CB:EB:F9:05:6F:D4:E7:DF:A8:EE:E4:00:2B`
  (registered in the Android OAuth client). The CI build fails if the APK's signer differs.
- **Signing:** `android/app/build.gradle` reads `~/.intervox/keystore.properties`
  (override with `INTERVOX_KEYSTORE_PROPERTIES`). The keystore and its passwords never
  go in the repo; `*.jks`, `*.keystore` and `keystore.properties` are gitignored.
  **Back up the keystore and passwords.** Losing them means future updates can't install
  over the app; you would have to uninstall and reinstall.

## Build in GitHub Actions (recommended)

The **Android APK** workflow builds and signs the release APK on Ubuntu with Node 22,
JDK 21 and Android SDK Platform 36 (`npm ci` → `npm run build:android` →
`./gradlew assembleRelease`). It runs:

- on demand: GitHub → **Actions** → **Android APK** → **Run workflow** (or
  `gh workflow run android.yml`), and
- on every push to `main` that changes `frontend/**` (or the workflow itself).

### Repository secrets (one time)

Add four secrets under **Settings → Secrets and variables → Actions → New repository
secret**, from the Mac that holds the release keystore, `~/Documents/keys/intervox.jks`
(alias `intervox`):

| Secret | Value |
|---|---|
| `KEYSTORE_BASE64` | the `.jks` file, base64-encoded |
| `KEYSTORE_PASSWORD` | `storePassword` |
| `KEY_ALIAS` | `keyAlias` (`intervox`) |
| `KEY_PASSWORD` | `keyPassword` |

On the website, get the `KEYSTORE_BASE64` value with
`base64 -i ~/Documents/keys/intervox.jks | pbcopy` and paste it. Or with `gh`:

```bash
# On the Mac, with gh logged in; each command reads the value from stdin or a prompt,
# so nothing lands in shell history.
base64 -i ~/Documents/keys/intervox.jks | gh secret set KEYSTORE_BASE64 -R HibahNafees/InterVox
gh secret set KEYSTORE_PASSWORD -R HibahNafees/InterVox    # paste storePassword
gh secret set KEY_ALIAS -R HibahNafees/InterVox            # type: intervox
gh secret set KEY_PASSWORD -R HibahNafees/InterVox         # paste keyPassword
```

### What the workflow does with them

- Decodes the keystore and writes `keystore.properties` into the runner's temp folder
  (`$RUNNER_TEMP`, mode 600), points Gradle at it with `INTERVOX_KEYSTORE_PROPERTIES`, and
  deletes both after the build. Nothing is committed or uploaded except the APK.
- Secrets are only passed as environment variables to that one step and are never
  echoed; GitHub also masks them in logs. A missing secret fails the run by name.
- After the build, `apksigner verify --print-certs` must show exactly one signer whose
  SHA-1 is the release fingerprint above; otherwise the run fails and no APK is uploaded.

### Version numbers

Each run sets the version from its run number (T-159): `versionCode` = 100 + run number,
`versionName` = `1.1.<run number>`. So every new run's APK is newer than the last one and
installs as an update, keeping your sign-in and data; you never edit `build.gradle` for a
CI release. The run checks the built APK's version with `aapt2` and fails if it's wrong.
Re-running the same run gives the same version.

### Download and install on the phone

1. Open the run → **Artifacts** → `intervox-apk-1.1.<run>` (kept 30 days). It downloads
   as a zip holding `intervox-1.1.<run>.apk`; unzip it.
2. Send the APK to the phone (e.g. email it to yourself, Google Drive, or a USB cable).
3. On the phone, open the file and tap **Update** (the first time, allow "Install unknown
   apps" for the app you opened it from). Settings → Apps → InterVox shows the new version.

Or from a computer: `adb install -r intervox-1.1.<run>.apk`, or
`gh run download -R HibahNafees/InterVox -n intervox-apk-1.1.<run>`.

CI and Mac builds use the same keystore, so either installs over the other, but Android
refuses a *lower* `versionCode`. A Mac build defaults to `versionCode` 2, below every CI
build, so to install one over a CI build, build it with a higher number:
`INTERVOX_VERSION_CODE=<higher> INTERVOX_VERSION_NAME=<name> ./gradlew assembleRelease`.

## Build on a Mac (fallback)

### Mac prerequisites (one time)

- Node 22+ (`node -v`)
- Android Studio, with Android SDK Platform 36 and Build-Tools installed (SDK Manager)
- JDK 21 (Android Studio's bundled JBR works)

```bash
export JAVA_HOME="/Applications/Android Studio.app/Contents/jbr/Contents/Home"
export ANDROID_HOME="$HOME/Library/Android/sdk"
export PATH="$ANDROID_HOME/platform-tools:$JAVA_HOME/bin:$PATH"
```

### Create the keystore (one time)

```bash
mkdir -p ~/Documents/keys ~/.intervox && chmod 700 ~/Documents/keys ~/.intervox
keytool -genkeypair -v -keystore ~/Documents/keys/intervox.jks \
  -alias intervox -keyalg RSA -keysize 2048 -validity 10000 \
  -dname "CN=InterVox, O=InterVox, C=US"
# keytool prompts for a password; reuse it below.
cat > ~/.intervox/keystore.properties <<EOF
storeFile=$HOME/Documents/keys/intervox.jks
storePassword=YOUR_PASSWORD
keyAlias=intervox
keyPassword=YOUR_PASSWORD
EOF
chmod 600 ~/.intervox/keystore.properties ~/Documents/keys/intervox.jks
```

### Build and install

```bash
git clone git@github.com:HibahNafees/InterVox.git ~/InterVox   # first time; later: git -C ~/InterVox pull
cd ~/InterVox/frontend
npm ci
npm run build:android                      # vite build (live API URL) + cap sync android
cd android && ./gradlew assembleRelease
apksigner verify --print-certs app/build/outputs/apk/release/app-release.apk
adb devices                                # phone: Developer options → USB debugging on
adb install -r app/build/outputs/apk/release/app-release.apk
```

`apksigner` lives in `$ANDROID_HOME/build-tools/<version>/`. If `assembleRelease`
produces `app-release-unsigned.apk`, Gradle did not find `~/.intervox/keystore.properties`.

For each Mac update, set `INTERVOX_VERSION_CODE` above the installed app's version code
(see *Version numbers*) so `adb install -r` keeps the app's data.
