// The interviewer's voice (voice stage 3).
// browser: the free Web Speech API speaks each message with the OS's voices.
// fire: Flask returns Fire audio clips per speaker segment; they play in order, and
// the browser voice takes over if a clip can't play.

import { isNativeApp } from './native'

const PREF_KEY = 'mi_voice'

// Persona → how the interviewer sounds. The role-play character gets its own voice.
const STYLES = {
  friendly: { rate: 1.0, pitch: 1.1 },
  neutral: { rate: 1.0, pitch: 1.0 },
  tough: { rate: 1.08, pitch: 0.85 },
}
const CHARACTER_STYLE = { rate: 1.0, pitch: 1.0 }

// Said while the answer is transcribed and the reply is written (hides the pause).
// Real words only: speech engines spell out sounds like "Mm-hm" letter by letter.
export const FILLERS = ['Okay.', 'Got it.', 'Right.', 'I see.', 'Alright.']

export function canSpeak() {
  return (
    typeof window !== 'undefined' &&
    'speechSynthesis' in window &&
    typeof window.SpeechSynthesisUtterance === 'function'
  )
}

// Whether this device should ask Flask for Fire audio: always with
// VOICE_PROVIDER=fire, and as the fallback (T-148) where the browser can't speak.
// The Android app's WebView has no reliable speech of its own, so it always uses Fire.
export function usesFireVoice(voice) {
  if (voice?.provider === 'fire') return true
  return Boolean(voice?.fire_fallback) && (isNativeApp() || !canSpeak())
}

export function voicePref() {
  try {
    return localStorage.getItem(PREF_KEY) !== 'off'
  } catch {
    return true
  }
}

export function setVoicePref(on) {
  try {
    localStorage.setItem(PREF_KEY, on ? 'on' : 'off')
  } catch {
    // Storage unavailable: the choice lasts for this page only.
  }
}

// Chrome loads its voice list asynchronously; ask early so it's ready to pick from.
export function warmUpVoices() {
  if (canSpeak()) window.speechSynthesis.getVoices?.()
}

function voicesForPage() {
  const all = window.speechSynthesis.getVoices?.() ?? []
  const lang = (navigator.language || 'en').slice(0, 2).toLowerCase()
  const mine = all.filter((v) => v.lang?.toLowerCase().startsWith(lang))
  return mine.length ? mine : all
}

// Two different voices when the system has them: interviewer and character.
export function pickVoices(voices) {
  const interviewer = voices.find((v) => v.default) ?? voices[0] ?? null
  const character = voices.find((v) => v !== interviewer) ?? interviewer
  return { interviewer, character }
}

// Panel interviewers in panel order (lead first), each with a different system
// voice while there are enough, else the same voice at a different pitch.
const PANEL_PITCH = [1.0, 0.85, 1.2]
export function panelVoices(voices, panel) {
  const lead = voices.find((v) => v.default) ?? voices[0] ?? null
  const others = voices.filter((v) => v !== lead)
  const out = {}
  ;(panel ?? []).forEach((p, i) => {
    const voice = i === 0 ? lead : (others[i - 1] ?? lead)
    out[p.key] = { voice, pitch: voice === lead && i > 0 ? PANEL_PITCH[i] : null }
  })
  return out
}

// Short utterances: Chrome cuts long ones off after ~15 seconds.
export function sentences(text) {
  return (text.match(/[^.!?]+[.!?]*/g) ?? []).map((s) => s.trim()).filter(Boolean)
}

function styleFor(who, persona, sameVoice) {
  const base = STYLES[persona] ?? STYLES.neutral
  if (who !== 'character') return base
  // Only one system voice: tell the character apart by pitch.
  return sameVoice ? { rate: 1.0, pitch: base.pitch > 1 ? 0.85 : 1.2 } : CHARACTER_STYLE
}

const SILENT = { done: Promise.resolve({ ok: true }), cancel() {} }
// Errors that just mean "stopped on purpose".
const STOPPED = ['interrupted', 'canceled']

// Speaks [{who, text}] in order. Returns { done, cancel }; done resolves to
// { ok: false } if the browser couldn't speak (no voices installed, autoplay blocked).
export function speakSegments(segments, persona = 'neutral', panel = null) {
  if (!canSpeak() || !segments?.length) return SILENT
  const synth = window.speechSynthesis
  synth.cancel()
  const available = voicesForPage()
  const { interviewer, character } = pickVoices(available)
  const panelists = panelVoices(available, panel)
  const utterances = segments.flatMap((seg) =>
    sentences(seg.text).map((text) => {
      const u = new window.SpeechSynthesisUtterance(text)
      const member = seg.who === 'interviewer' ? panelists[seg.panelist] : null
      const voice = member ? member.voice : seg.who === 'character' ? character : interviewer
      if (voice) u.voice = voice
      const { rate, pitch } = styleFor(seg.who, persona, character === interviewer)
      u.rate = rate
      u.pitch = member?.pitch ?? pitch
      return u
    }),
  )
  if (!utterances.length) return SILENT
  let finish
  const done = new Promise((resolve) => {
    finish = resolve
  })
  // One failed sentence means the rest will fail too: stop waiting.
  utterances.forEach((u) => {
    u.onerror = (e) => finish({ ok: STOPPED.includes(e?.error) })
  })
  utterances[utterances.length - 1].onend = () => finish({ ok: true })
  utterances.forEach((u) => synth.speak(u))
  return {
    done,
    cancel() {
      synth.cancel()
      finish({ ok: true })
    },
  }
}

// Plays Fire clips [{who, audio}] in order; falls back to the browser voice.
export function playClips(clips, segments, persona, panel) {
  let audio = null
  let fallback = null
  let stopped = false
  let finish
  const done = new Promise((resolve) => {
    finish = resolve
  })
  ;(async () => {
    let result = { ok: true }
    for (const clip of clips) {
      if (stopped) break
      audio = new Audio(clip.audio)
      try {
        await new Promise((resolve, reject) => {
          audio.onended = resolve
          audio.onerror = reject
          audio.play().catch(reject)
        })
      } catch {
        if (!stopped) {
          fallback = speakSegments(segments, persona, panel)
          result = await fallback.done
        }
        break
      }
    }
    finish(result)
  })()
  return {
    done,
    cancel() {
      stopped = true
      audio?.pause()
      fallback?.cancel()
      finish({ ok: true })
    },
  }
}

// One interviewer message: Fire clips when the backend sent them, else the browser.
export function say({ segments, clips, persona, panel }) {
  if (clips?.length) return playClips(clips, segments, persona, panel)
  return speakSegments(segments, persona, panel)
}
