# InterVox Android app (Capacitor)

The Android app wraps the same Vite frontend with Capacitor 8 (`frontend/android`,
`frontend/capacitor.config.json`). It ships the built web files inside the APK and
calls the live API at `https://intervox.duckdns.org`. It is built on a Mac (the devbox
has no Android SDK). Ticket: T-147.

- **App id:** `site.intervox.app` · **name:** InterVox
- **WebView origin:** `https://app.intervox.site`. The live API must list it in
  `CORS_ORIGINS` (`localhost` origins are refused in production). Nothing is hosted at
  that name; it only labels the app's origin.
- **Permissions:** microphone (answers), camera (opt-in body language), internet.
- **Interviewer voice:** Android WebView has no Web Speech synthesis, so the browser
  voice is unavailable in the app and replies stay text. Fire voice (`VOICE_PROVIDER=fire`)
  still plays.
- **Signing:** `android/app/build.gradle` reads `~/.intervox/keystore.properties`
  (override with `INTERVOX_KEYSTORE_PROPERTIES`). The keystore and its passwords never
  go in the repo; `*.jks`, `*.keystore` and `keystore.properties` are gitignored.
  **Back up the keystore and passwords.** Losing them means future updates can't install
  over the app; you would have to uninstall and reinstall.

## Mac prerequisites (one time)

- Node 22+ (`node -v`)
- Android Studio, with Android SDK Platform 36 and Build-Tools installed (SDK Manager)
- JDK 21 (Android Studio's bundled JBR works)

```bash
export JAVA_HOME="/Applications/Android Studio.app/Contents/jbr/Contents/Home"
export ANDROID_HOME="$HOME/Library/Android/sdk"
export PATH="$ANDROID_HOME/platform-tools:$JAVA_HOME/bin:$PATH"
```

## Create the keystore (one time)

```bash
mkdir -p ~/.intervox && chmod 700 ~/.intervox
keytool -genkeypair -v -keystore ~/.intervox/intervox-release.jks \
  -alias intervox -keyalg RSA -keysize 2048 -validity 10000 \
  -dname "CN=InterVox, O=InterVox, C=US"
# keytool prompts for a password; reuse it below.
cat > ~/.intervox/keystore.properties <<EOF
storeFile=$HOME/.intervox/intervox-release.jks
storePassword=YOUR_PASSWORD
keyAlias=intervox
keyPassword=YOUR_PASSWORD
EOF
chmod 600 ~/.intervox/keystore.properties ~/.intervox/intervox-release.jks
```

## Build and install

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

For each update, bump `versionCode` (and `versionName`) in `android/app/build.gradle`
before building so `adb install -r` keeps the app's data.
