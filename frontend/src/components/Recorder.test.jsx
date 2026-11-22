import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import Recorder from './Recorder'
import { isNativeApp } from '../lib/native'

vi.mock('../lib/native', () => ({ isNativeApp: vi.fn(() => false) }))

class FakeMediaRecorder {
  static isTypeSupported = (t) => t === 'audio/webm;codecs=opus'
  constructor(stream, opts) {
    this.stream = stream
    this.mimeType = opts.mimeType
    this.opts = opts
    this.state = 'inactive'
    FakeMediaRecorder.last = this
  }
  start() {
    this.state = 'recording'
  }
  stop() {
    this.state = 'inactive'
    this.ondataavailable({ data: new Blob(['abc'], { type: this.mimeType }) })
    this.onstop()
  }
}

let level = 0
class FakeAudioContext {
  createAnalyser() {
    return {
      fftSize: 0,
      getFloatTimeDomainData: (buf) => buf.fill(level),
    }
  }
  createMediaStreamSource() {
    return { connect() {} }
  }
  close() {}
}

const track = { stop: vi.fn() }

beforeEach(() => {
  level = 0
  track.stop.mockClear()
  vi.stubGlobal('MediaRecorder', FakeMediaRecorder)
  vi.stubGlobal('AudioContext', FakeAudioContext)
  Object.defineProperty(navigator, 'mediaDevices', {
    configurable: true,
    value: { getUserMedia: vi.fn(async () => ({ getTracks: () => [track] })) },
  })
})

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe('Recorder', () => {
  it('records until Done and hands over the clip', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const onRecorded = vi.fn()
    render(<Recorder onRecorded={onRecorded} />)
    await act(async () => screen.getByRole('button', { name: 'Record answer' }).click())
    expect(FakeMediaRecorder.last.opts.audioBitsPerSecond).toBe(32000)
    await act(async () => vi.advanceTimersByTime(1500))
    await act(async () => screen.getByRole('button', { name: 'Done' }).click())

    expect(onRecorded).toHaveBeenCalledTimes(1)
    const [blob, duration] = onRecorded.mock.calls[0]
    expect(blob.type).toBe('audio/webm;codecs=opus')
    expect(duration).toBeGreaterThanOrEqual(0)
    expect(track.stop).toHaveBeenCalled() // microphone released
  })

  it('hands the clip to the latest onRecorded, not the one from when recording began', async () => {
    // The page re-renders while the candidate talks (typing code); the old
    // callback would send the editor as it was at the start: empty.
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const first = vi.fn()
    const latest = vi.fn()
    const { rerender } = render(<Recorder onRecorded={first} />)
    await act(async () => screen.getByRole('button', { name: 'Record answer' }).click())
    rerender(<Recorder onRecorded={latest} />)
    await act(async () => vi.advanceTimersByTime(1500))
    await act(async () => screen.getByRole('button', { name: 'Done' }).click())

    expect(first).not.toHaveBeenCalled()
    expect(latest).toHaveBeenCalledTimes(1)
  })

  it('cancel discards the clip', async () => {
    const onRecorded = vi.fn()
    render(<Recorder onRecorded={onRecorded} />)
    await userEvent.click(screen.getByRole('button', { name: 'Record answer' }))
    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(onRecorded).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Record answer' })).toBeInTheDocument()
  })

  async function autoStop(onRecorded) {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    render(<Recorder onRecorded={onRecorded} />)
    await act(async () => screen.getByRole('button', { name: 'Record answer' }).click())
    await act(async () => vi.advanceTimersByTime(700)) // calibrate on silence
    level = 0.3
    await act(async () => vi.advanceTimersByTime(6000)) // a settled answer
    level = 0
    await act(async () => vi.advanceTimersByTime(2000))
    expect(screen.getByRole('status')).toHaveTextContent('Stopping in')
    await act(async () => vi.advanceTimersByTime(2500))
  }

  it('waits longer through a thinking pause early in an answer (T-88)', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const onRecorded = vi.fn()
    render(<Recorder onRecorded={onRecorded} />)
    await act(async () => screen.getByRole('button', { name: 'Record answer' }).click())
    await act(async () => vi.advanceTimersByTime(700))
    level = 0.3
    await act(async () => vi.advanceTimersByTime(1000)) // "So, when I worked..."
    level = 0
    await act(async () => vi.advanceTimersByTime(5000)) // thinking
    expect(screen.getByRole('button', { name: 'Done' })).toBeInTheDocument() // still recording
    await act(async () => screen.getByRole('button', { name: 'Cancel' }).click())
    await act(async () => vi.advanceTimersByTime(5000))
    expect(onRecorded).not.toHaveBeenCalled()
  })

  it('stops by itself after speech then silence, and sends after a short wait', async () => {
    const onRecorded = vi.fn()
    await autoStop(onRecorded)
    // T-32: a moment to discard before it is sent.
    expect(onRecorded).not.toHaveBeenCalled()
    expect(screen.getByRole('status')).toHaveTextContent('Sending your answer in')
    await act(async () => vi.advanceTimersByTime(3100))
    expect(onRecorded).toHaveBeenCalledTimes(1)
    expect(screen.getByRole('button', { name: 'Record answer' })).toBeInTheDocument()
  })

  it('when time runs out, says so at once and sends what was said, marked cut off', async () => {
    // T-109: pressure mode's limit (and the 5-minute cap) stop the answer politely.
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const onRecorded = vi.fn()
    const onTimeUp = vi.fn()
    render(<Recorder onRecorded={onRecorded} onTimeUp={onTimeUp} limitMs={2000} />)
    await act(async () => screen.getByRole('button', { name: 'Record answer' }).click())
    level = 0.2 // still talking
    await act(async () => vi.advanceTimersByTime(2200))
    expect(onTimeUp).toHaveBeenCalledTimes(1)
    expect(onRecorded).toHaveBeenCalledTimes(1) // no undo window
    expect(onRecorded.mock.calls[0][2]).toEqual({ cutOff: true })
  })

  it('an auto-stopped answer can be discarded', async () => {
    const onRecorded = vi.fn()
    await autoStop(onRecorded)
    await act(async () => screen.getByRole('button', { name: 'Cancel' }).click())
    await act(async () => vi.advanceTimersByTime(5000))
    expect(onRecorded).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Record answer' })).toBeInTheDocument()
  })

  it('an auto-stopped answer can be sent at once', async () => {
    const onRecorded = vi.fn()
    await autoStop(onRecorded)
    await act(async () => screen.getByRole('button', { name: 'Send now' }).click())
    expect(onRecorded).toHaveBeenCalledTimes(1)
  })

  it('does not send an accidental tap', async () => {
    const onRecorded = vi.fn()
    render(<Recorder onRecorded={onRecorded} />)
    await userEvent.click(screen.getByRole('button', { name: 'Record answer' }))
    await userEvent.click(screen.getByRole('button', { name: 'Done' }))
    expect(onRecorded).not.toHaveBeenCalled()
    expect(screen.getByRole('alert')).toHaveTextContent('too short')
  })

  it('explains a blocked microphone', async () => {
    navigator.mediaDevices.getUserMedia = vi.fn(async () => {
      throw Object.assign(new Error('denied'), { name: 'NotAllowedError' })
    })
    render(<Recorder onRecorded={vi.fn()} />)
    await userEvent.click(screen.getByRole('button', { name: 'Record answer' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Microphone access was blocked')
  })

  it('points to Android settings when the app is blocked from the microphone', async () => {
    isNativeApp.mockReturnValue(true)
    navigator.mediaDevices.getUserMedia = vi.fn(async () => {
      throw Object.assign(new Error('denied'), { name: 'NotAllowedError' })
    })
    render(<Recorder onRecorded={vi.fn()} />)
    await userEvent.click(screen.getByRole('button', { name: 'Record answer' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Settings → Apps → InterVox → Permissions')
    isNativeApp.mockReturnValue(false)
  })

  it('starts by itself when asked, once it is free', async () => {
    const onRecorded = vi.fn()
    const { rerender } = render(<Recorder onRecorded={onRecorded} disabled autoStartKey={1} />)
    expect(screen.getByRole('button', { name: 'Record answer' })).toBeInTheDocument()
    rerender(<Recorder onRecorded={onRecorded} autoStartKey={1} />)
    expect(await screen.findByRole('button', { name: 'Done' })).toBeInTheDocument()
  })
})
