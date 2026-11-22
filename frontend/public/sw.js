// InterVox service worker (T-149). It caches the app shell only: the start page,
// the hashed build files, the manifest and the icons. Never API responses, never
// user data, never shared report links, never anything from another origin (the
// API is on another origin). Bump VERSION to drop every old cache.
const VERSION = 'v1'
const CACHE = `intervox-shell-${VERSION}`
const SHELL = ['/', '/manifest.webmanifest', '/favicon.svg', '/icons/icon-192.png', '/icons/icon-512.png']
const MAX_ASSETS = 80

// Whether a non-navigation request may be served from / stored in the cache.
function shouldCache(request, origin) {
  if (request.method !== 'GET') return false
  const url = new URL(request.url)
  if (url.origin !== origin) return false
  if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/shared/')) return false
  return url.pathname.startsWith('/assets/') || url.pathname.startsWith('/icons/') || SHELL.includes(url.pathname)
}

async function trim(cache) {
  const keys = (await cache.keys()).filter((r) => new URL(r.url).pathname.startsWith('/assets/'))
  await Promise.all(keys.slice(0, Math.max(0, keys.length - MAX_ASSETS)).map((r) => cache.delete(r)))
}

async function cacheFirst(request) {
  const cache = await caches.open(CACHE)
  const hit = await cache.match(request)
  if (hit) return hit
  const response = await fetch(request)
  if (response.ok && response.type === 'basic') {
    await cache.put(request, response.clone())
    trim(cache)
  }
  return response
}

// Pages always come from the network when online (fresh build). Offline, any
// page gets the cached shell; only the start page itself refreshes that copy.
async function page(request) {
  try {
    const response = await fetch(request)
    if (response.ok && new URL(request.url).pathname === '/') {
      const cache = await caches.open(CACHE)
      await cache.put('/', response.clone())
    }
    return response
  } catch (err) {
    const shell = await caches.match('/')
    if (shell) return shell
    throw err
  }
}

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches
      .open(CACHE)
      .then((cache) => cache.addAll(SHELL))
      .then(() => self.skipWaiting()),
  )
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  )
})

self.addEventListener('fetch', (event) => {
  const request = event.request
  const url = new URL(request.url)
  if (request.mode === 'navigate') {
    if (url.origin === self.location.origin && !url.pathname.startsWith('/api/')) {
      event.respondWith(page(request))
    }
    return
  }
  if (shouldCache(request, self.location.origin)) event.respondWith(cacheFirst(request))
})
