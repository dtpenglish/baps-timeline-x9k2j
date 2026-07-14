// service-worker.js  v1.0
// =========================
// Strategy:
//   - App shell (index.html, icons): stale-while-revalidate so the app
//     opens instantly but updates show up on next visit.
//   - events.json: NETWORK FIRST, never cached long-term. This is the
//     "live data" — we want fresh content, falling back to cache only
//     if offline.
//   - photos/: cache on first view, serve from cache forever after.
//   - R2 media (videos, audio): NEVER cached by the service worker.
//     Files are large (up to 145 MB) and cache eviction would be messy.
//     The browser's HTTP cache handles them naturally.
//   - Everything else: network-first with cache fallback.

const SHELL_CACHE  = 'baps-shell-v1';
const PHOTO_CACHE  = 'baps-photos-v1';
const DATA_CACHE   = 'baps-data-v1';

const SHELL_FILES = [
  './',
  './index.html',
  './manifest.json',
  './icons/icon-192.png',
  './icons/icon-512.png',
  './icons/icon-180.png',
  './images/akshar-logo_1.png',
  './images/akshar-logo_2.png',
];

// On install: pre-cache the app shell.
self.addEventListener('install', evt => {
  evt.waitUntil(
    caches.open(SHELL_CACHE).then(cache =>
      // addAll fails atomically if any one file fails; use individual
      // adds with .catch so missing icons don't kill installation.
      Promise.all(SHELL_FILES.map(url =>
        cache.add(url).catch(err => console.warn('SW: failed to cache', url, err))
      ))
    ).then(() => self.skipWaiting())
  );
});

// On activate: clean up old cache versions.
self.addEventListener('activate', evt => {
  const allowed = new Set([SHELL_CACHE, PHOTO_CACHE, DATA_CACHE]);
  evt.waitUntil(
    caches.keys().then(keys => Promise.all(
      keys.filter(k => !allowed.has(k)).map(k => caches.delete(k))
    )).then(() => self.clients.claim())
  );
});

// Helpers ─────────────────────────────────────────────────────────
function isPhoto(url) {
  return /\/photos\/.+\.(jpg|jpeg|png|webp|gif)$/i.test(url.pathname);
}
function isEventsJson(url) {
  // events.json plus lazy data layers (e.g. events-vicharan.json) —
  // all are live data: network-first, cached per-path for offline.
  return /\/?events(-[a-z0-9]+)?\.json$/i.test(url.pathname);
}
function isLargeMedia(url) {
  // R2-hosted media: don't intercept, let browser handle.
  return /\.(mp4|webm|mp3|wav|m4a|pdf)$/i.test(url.pathname);
}

// Fetch handler ───────────────────────────────────────────────────
self.addEventListener('fetch', evt => {
  const req = evt.request;
  const url = new URL(req.url);

  // Only handle GET requests
  if (req.method !== 'GET') return;

  // Don't intercept large media — let the browser stream it directly.
  if (isLargeMedia(url)) return;

  // Don't intercept cross-origin fonts/CDN scripts.
  if (url.origin !== self.location.origin) return;

  // events.json: network-first, fall back to cache if offline.
  if (isEventsJson(url)) {
    evt.respondWith(
      fetch(req).then(resp => {
        // Stash a copy for offline use, keyed by path so each data
        // layer caches independently.
        const copy = resp.clone();
        caches.open(DATA_CACHE).then(c => c.put(url.pathname, copy));
        return resp;
      }).catch(() => caches.open(DATA_CACHE).then(c => c.match(url.pathname)))
    );
    return;
  }

  // Photos: cache-first, lazy fill.
  if (isPhoto(url)) {
    evt.respondWith(
      caches.open(PHOTO_CACHE).then(cache =>
        cache.match(req).then(hit => {
          if (hit) return hit;
          return fetch(req).then(resp => {
            // Only cache successful responses.
            if (resp.ok) cache.put(req, resp.clone());
            return resp;
          });
        })
      )
    );
    return;
  }

  // App shell + everything else: stale-while-revalidate.
  evt.respondWith(
    caches.open(SHELL_CACHE).then(cache =>
      cache.match(req).then(hit => {
        const fetchPromise = fetch(req).then(resp => {
          if (resp.ok) cache.put(req, resp.clone());
          return resp;
        }).catch(() => hit); // offline → return whatever we have
        return hit || fetchPromise;
      })
    )
  );
});
