// Installable web app (T-149): service worker registration and the install prompt.
import { useEffect, useState } from 'react'
import { isNativeApp } from './native'

const DISMISS_KEY = 'mi_install_dismissed'
let deferred = null // the browser's saved beforeinstallprompt event
const listeners = new Set()
const changed = () => listeners.forEach((fn) => fn())

// The website only: never in dev (stale builds) or the Android app (files are local).
export function registerServiceWorker({ prod = import.meta.env.PROD } = {}) {
  if (!prod || isNativeApp() || typeof navigator === 'undefined' || !('serviceWorker' in navigator)) return false
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => {})
  })
  return true
}

// Called once at startup, before React: the event can fire early.
export function listenForInstall() {
  window.addEventListener('beforeinstallprompt', (e) => {
    e.preventDefault()
    deferred = e
    changed()
  })
  window.addEventListener('appinstalled', () => {
    deferred = null
    changed()
  })
}

function installed() {
  return (
    isNativeApp() ||
    window.matchMedia?.('(display-mode: standalone)').matches ||
    window.navigator.standalone === true
  )
}

function isIos() {
  const ua = window.navigator.userAgent || ''
  return /iPhone|iPad|iPod/.test(ua) || (ua.includes('Macintosh') && navigator.maxTouchPoints > 1)
}

function dismissedBefore() {
  try {
    return localStorage.getItem(DISMISS_KEY) === '1'
  } catch {
    return false
  }
}

// { mode: 'prompt' | 'ios' | null, install(), dismiss() }
export function useInstallPrompt() {
  const [, bump] = useState(0)
  const [dismissed, setDismissed] = useState(dismissedBefore)
  useEffect(() => {
    const fn = () => bump((n) => n + 1)
    listeners.add(fn)
    return () => listeners.delete(fn)
  }, [])
  let mode = null
  if (!dismissed && !installed()) mode = deferred ? 'prompt' : isIos() ? 'ios' : null
  return {
    mode,
    async install() {
      const e = deferred
      if (!e) return
      deferred = null
      changed()
      await e.prompt()
    },
    dismiss() {
      try {
        localStorage.setItem(DISMISS_KEY, '1')
      } catch {
        // Storage unavailable: hidden for this page only.
      }
      setDismissed(true)
    },
  }
}
