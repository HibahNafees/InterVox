import { afterEach, describe, expect, it, vi } from 'vitest'
import { ALEX, SAM, fakeSpeech } from '../test-speech'
import { isNativeApp } from './native'
import {
  panelVoices,
  pickVoices,
  playClips,
  say,
  sentences,
  speakSegments,
  usesFireVoice,
  voicePref,
  setVoicePref,
} from './voice'

vi.mock('./native', () => ({ isNativeApp: vi.fn(() => false) }))

afterEach(() => vi.unstubAllGlobals())

describe('browser voice', () => {
  it('splits text into sentences so long replies are not cut off', () => {
    expect(sentences('Hi there. How are you? Fine!')).toEqual(['Hi there.', 'How are you?', 'Fine!'])
    expect(sentences('No punctuation')).toEqual(['No punctuation'])
  })

  it('gives the interviewer and the character different voices', () => {
    expect(pickVoices([SAM, ALEX])).toEqual({ interviewer: ALEX, character: SAM })
    expect(pickVoices([ALEX])).toEqual({ interviewer: ALEX, character: ALEX })
    expect(pickVoices([])).toEqual({ interviewer: null, character: null })
  })

  it('speaks each segment in its speaker voice and persona style', async () => {
    const spoken = fakeSpeech()
    const handle = speakSegments(
      [
        { who: 'interviewer', text: "Let's switch to a role-play." },
        { who: 'character', text: 'Too expensive. Convince me.' },
      ],
      'tough',
    )
    expect(spoken.map((u) => [u.text, u.voice.name])).toEqual([
      ["Let's switch to a role-play.", 'Alex'],
      ['Too expensive.', 'Sam'],
      ['Convince me.', 'Sam'],
    ])
    expect(spoken[0].pitch).toBeLessThan(1) // tough interviewer
    expect(spoken[1].pitch).toBe(1)
    spoken.at(-1).onend()
    await handle.done
  })

  it('tells the character apart by pitch when there is only one voice', () => {
    const spoken = fakeSpeech([ALEX])
    speakSegments([{ who: 'character', text: 'Hello.' }], 'neutral')
    expect(spoken[0].pitch).not.toBe(1)
  })

  it('gives each panel interviewer their own voice, or pitch', () => {
    const panel = [{ key: 'hm' }, { key: 'peer' }, { key: 'hr' }]
    expect(panelVoices([SAM, ALEX], panel)).toEqual({
      hm: { voice: ALEX, pitch: null },
      peer: { voice: SAM, pitch: null },
      hr: { voice: ALEX, pitch: 1.2 },
    })
    const spoken = fakeSpeech()
    speakSegments(
      [
        { who: 'interviewer', panelist: 'hm', text: 'Over to Marcus.' },
        { who: 'interviewer', panelist: 'peer', text: 'Hi, Marcus here.' },
      ],
      'neutral',
      panel.slice(0, 2),
    )
    expect(spoken.map((u) => u.voice.name)).toEqual(['Alex', 'Sam'])
  })

  it('stops at once when cancelled', async () => {
    fakeSpeech()
    const handle = speakSegments([{ who: 'interviewer', text: 'A long question.' }])
    handle.cancel()
    await handle.done
    expect(window.speechSynthesis.cancel).toHaveBeenCalled()
  })

  it('reports when the browser cannot speak', async () => {
    const spoken = fakeSpeech([])
    const handle = speakSegments([{ who: 'interviewer', text: 'One. Two.' }])
    spoken[0].onerror({ error: 'synthesis-failed' })
    expect(await handle.done).toEqual({ ok: false })
  })

  it('is silent without speech support', async () => {
    await speakSegments([{ who: 'interviewer', text: 'Hi.' }]).done
  })

  it('remembers the on/off choice', () => {
    expect(voicePref()).toBe(true)
    setVoicePref(false)
    expect(voicePref()).toBe(false)
  })
})

describe('Fire voice', () => {
  function fakeAudio({ fail = false } = {}) {
    const played = []
    vi.stubGlobal('Audio', class {
      constructor(src) {
        this.src = src
        played.push(this)
      }
      play() {
        if (fail) return Promise.reject(new Error('blocked'))
        setTimeout(() => this.onended())
        return Promise.resolve()
      }
      pause() {}
    })
    return played
  }

  it('plays the clips in order', async () => {
    const played = fakeAudio()
    const clips = [
      { who: 'interviewer', audio: 'data:audio/mpeg;base64,AA' },
      { who: 'character', audio: 'data:audio/mpeg;base64,BB' },
    ]
    await say({ segments: [], clips, persona: 'neutral' }).done
    expect(played.map((a) => a.src)).toEqual(clips.map((c) => c.audio))
  })

  it('falls back to the browser voice if a clip cannot play', async () => {
    fakeAudio({ fail: true })
    const spoken = fakeSpeech()
    const handle = playClips(
      [{ who: 'interviewer', audio: 'data:audio/mpeg;base64,AA' }],
      [{ who: 'interviewer', text: 'Tell me about Acme.' }],
      'neutral',
    )
    await vi.waitFor(() => expect(spoken.map((u) => u.text)).toEqual(['Tell me about Acme.']))
    spoken[0].onend()
    await handle.done
  })
})

describe('Fire voice fallback (T-148)', () => {
  const browser = { provider: 'browser', fire_fallback: true }

  it('uses Fire when the server says so', () => {
    expect(usesFireVoice({ provider: 'fire' })).toBe(true)
  })

  it('uses Fire only where the browser cannot speak', () => {
    expect(usesFireVoice(browser)).toBe(true) // jsdom: no speechSynthesis
    fakeSpeech()
    expect(usesFireVoice(browser)).toBe(false)
    expect(usesFireVoice({ ...browser, fire_fallback: false })).toBe(false)
    expect(usesFireVoice(undefined)).toBe(false)
  })

  it('always uses Fire in the Android app when the fallback is on', () => {
    fakeSpeech()
    isNativeApp.mockReturnValue(true)
    expect(usesFireVoice(browser)).toBe(true)
    expect(usesFireVoice({ ...browser, fire_fallback: false })).toBe(false)
    isNativeApp.mockReturnValue(false)
  })
})
