const CACHE = 'brainwreck-v2';
const ASSETS = [
  'https://hermesandroid.github.io/brainwreck/',
  'https://hermesandroid.github.io/brainwreck/index.html',
  'https://hermesandroid.github.io/brainwreck/manifest.json',
];

// Install — cache assets
self.addEventListener('install', e => {
  self.skipWaiting(); // activate immediately
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(ASSETS)));
});

// Activate — clear old caches, claim clients
self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

// Fetch — network-first for HTML, cache for static
self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);
  // Always go network for the main page (gets latest version)
  if (url.pathname.endsWith('/') || url.pathname.endsWith('index.html')) {
    e.respondWith(
      fetch(e.request).catch(() => caches.match(e.request))
    );
    return;
  }
  // Cache-first for everything else
  e.respondWith(
    caches.match(e.request).then(r => r || fetch(e.request))
  );
});

// Check for updates every 10 minutes
self.addEventListener('message', e => {
  if (e.data === 'check-update') {
    self.registration.update();
  }
});
