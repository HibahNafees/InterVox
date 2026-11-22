#!/usr/bin/env bash
# Renders the InterVox logo (public/favicon.svg) into the PWA icons and the Android
# launcher icons + splash screens (T-149, T-151). Needs rsvg-convert and ImageMagick.
# Run from anywhere: frontend/scripts/icons.sh
set -euo pipefail
cd "$(dirname "$0")/.."

CREAM='#fffaf4'
CORAL='#f7715c'
RES=android/app/src/main/res
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

DEFS='<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#fd7c68"/><stop offset="0.55" stop-color="#f7715c"/><stop offset="1" stop-color="#fdc458"/></linearGradient></defs>'
# The speech bubble with a voice level inside, centred on (32, 34) in a 64-unit box.
GLYPH='<path d="M14 15h36a6 6 0 0 1 6 6v18a6 6 0 0 1-6 6H29l-10 8v-8h-5a6 6 0 0 1-6-6V21a6 6 0 0 1 6-6z" fill="#fff"/><g fill="#023350"><rect x="18" y="26" width="5" height="8" rx="2.5"/><rect x="26" y="21" width="5" height="18" rx="2.5"/><rect x="34" y="24" width="5" height="12" rx="2.5"/><rect x="42" y="27" width="5" height="6" rx="2.5"/></g>'
glyph_at() { echo "<g transform=\"translate(32 32) scale($1) translate(-32 -34)\">$GLYPH</g>"; }

svg() { echo "<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 64 64\">$DEFS$1</svg>"; }
# Full-bleed gradient square: Android/Chrome masks it to their own shape.
svg "<rect width=\"64\" height=\"64\" fill=\"url(#g)\"/>$(glyph_at 0.72)" > "$TMP/maskable.svg"
# Circle for the legacy round launcher icon.
svg "<circle cx=\"32\" cy=\"32\" r=\"32\" fill=\"url(#g)\"/>$(glyph_at 0.72)" > "$TMP/round.svg"
# Adaptive icon foreground: glyph only, inside the 66/108 safe zone.
svg "$(glyph_at 0.6)" > "$TMP/foreground.svg"

render() { rsvg-convert -w "$2" -h "$2" "$1" -o "$3"; }

# PWA
mkdir -p public/icons
render public/favicon.svg 192 public/icons/icon-192.png
render public/favicon.svg 512 public/icons/icon-512.png
render "$TMP/maskable.svg" 512 public/icons/maskable-512.png

# Android launcher icons (48dp legacy, 108dp adaptive foreground)
for pair in mdpi:1 hdpi:1.5 xhdpi:2 xxhdpi:3 xxxhdpi:4; do
  d=${pair%%:*} f=${pair##*:}
  legacy=$(python3 -c "print(round(48*$f))")
  adaptive=$(python3 -c "print(round(108*$f))")
  render public/favicon.svg "$legacy" "$RES/mipmap-$d/ic_launcher.png"
  render "$TMP/round.svg" "$legacy" "$RES/mipmap-$d/ic_launcher_round.png"
  render "$TMP/foreground.svg" "$adaptive" "$RES/mipmap-$d/ic_launcher_foreground.png"
done
cat > "$RES/values/ic_launcher_background.xml" <<XML
<?xml version="1.0" encoding="utf-8"?>
<resources>
    <color name="ic_launcher_background">${CORAL^^}</color>
    <color name="splash_background">${CREAM^^}</color>
</resources>
XML

# Splash screens (Android 11 and older): the logo centred on cream, same sizes as before.
render public/favicon.svg 512 "$TMP/logo.png"
for f in "$RES"/drawable*/splash.png; do
  size=$(identify -format '%wx%h' "$f")
  short=$(identify -format '%[fx:min(w,h)]' "$f")
  logo=$((short * 3 / 10))
  convert -size "$size" "xc:$CREAM" \( "$TMP/logo.png" -resize "${logo}x${logo}" \) \
    -gravity center -composite -strip "$f"
done
echo "Icons written."
