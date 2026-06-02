const CACHE = 'training-cal-v2';
const PRECACHE = ['/'];

self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE).then(c => c.addAll(PRECACHE)).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', e => {
  // Network first for API calls, cache first for assets
  const url = new URL(e.request.url);
  const isApi = url.hostname.includes('supabase') ||
                url.hostname.includes('strava') ||
                url.hostname.includes('met.no') ||
                url.hostname.includes('google');

  if (isApi || e.request.method !== 'GET') return; // don't cache API calls

  e.respondWith(
    fetch(e.request)
      .then(res => {
        const clone = res.clone();
        caches.open(CACHE).then(c => c.put(e.request, clone));
        return res;
      })
      .catch(() => caches.match(e.request))
  );
});

// ── PUSH NOTIFICATIONS ──────────────────────────────────────────────────────
self.addEventListener('push', e => {
  let data = {};
  try {
    data = e.data ? e.data.json() : {};
  } catch (err) {
    data = { body: e.data ? e.data.text() : 'New items added' };
  }

  const title = data.title || '🛒 Shopping list';
  const options = {
    body:  data.body  || 'New items were added to the list',
    icon:  data.icon  || '/icon-192.png',
    badge: data.badge || '/icon-192.png',
    tag:   data.tag   || 'shopping-update', // same tag → replaces, doesn't stack
    renotify: true,
    data:  { url: data.url || '/' }
  };

  e.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener('notificationclick', e => {
  e.notification.close();
  const url = (e.notification.data && e.notification.data.url) || '/';
  e.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(list => {
      for (const client of list) {
        if ('focus' in client) return client.focus();
      }
      if (self.clients.openWindow) return self.clients.openWindow(url);
    })
  );
});
