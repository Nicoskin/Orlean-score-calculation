/* Service worker счётного листа: за столом интернета может не быть,
   поэтому всё, что нужно для работы, лежит в кэше.

   Стратегии:
   - страница — сначала сеть, потом кэш: так обновления доезжают при перезагрузке,
     а без сети открывается сохранённая копия;
   - свои картинки — сначала кэш (они неизменны в рамках версии), с тихим
     обновлением в фоне;
   - шрифты Google — сначала кэш, иначе качаем и кладём в кэш. Если их ещё нет,
     страница просто отрисуется запасными шрифтами, это не ломает работу. */

const VERSION = 'v2';
const SHELL = 'orleans-shell-' + VERSION;
const FONTS = 'orleans-fonts-' + VERSION;

const GOODS = ['grain', 'cheese', 'wine', 'wool', 'brocade'];
const CHARS = ['farmer', 'sailor', 'craftsman', 'merchant', 'knight', 'scholar', 'monk'];
const ASSETS = [
  './', './index.html', './manifest.webmanifest',
  './img/parchment.jpg', './img/icon.png', './img/icon-192.png', './img/icon-512.png',
  './img/coin.png', './img/station.png', './img/citizen.png', './img/star.png',
  ...GOODS.map(g => `./img/${g}.png`),
  ...GOODS.map(g => `./img/tile-${g}.jpg`),
  ...CHARS.map(c => `./img/ch-${c}.png`)
];

self.addEventListener('install', e => {
  e.waitUntil((async () => {
    const cache = await caches.open(SHELL);
    /* по одному: если один файл вдруг не найдётся, установка не должна падать целиком */
    await Promise.allSettled(ASSETS.map(u => cache.add(new Request(u, {cache: 'reload'}))));
    self.skipWaiting();
  })());
});

self.addEventListener('activate', e => {
  e.waitUntil((async () => {
    const keep = [SHELL, FONTS];
    await Promise.all((await caches.keys()).map(k => keep.includes(k) ? null : caches.delete(k)));
    await self.clients.claim();
  })());
});

const putCopy = (cacheName, req, res) => {
  if (res && (res.ok || res.type === 'opaque')) {
    const copy = res.clone();
    caches.open(cacheName).then(c => c.put(req, copy)).catch(() => {});
  }
  return res;
};

self.addEventListener('fetch', e => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);

  if (req.mode === 'navigate') {
    e.respondWith((async () => {
      try { return putCopy(SHELL, req, await fetch(req)); }
      catch (err) {
        return (await caches.match(req)) || (await caches.match('./index.html'))
          || new Response('Нет сети и нет сохранённой копии.', {status: 503, headers: {'Content-Type': 'text/plain; charset=utf-8'}});
      }
    })());
    return;
  }

  if (url.origin === location.origin) {
    e.respondWith((async () => {
      const hit = await caches.match(req);
      if (hit) { fetch(req).then(r => putCopy(SHELL, req, r)).catch(() => {}); return hit; }
      try { return putCopy(SHELL, req, await fetch(req)); }
      catch (err) { return new Response('', {status: 504}); }
    })());
    return;
  }

  if (/fonts\.(googleapis|gstatic)\.com$/.test(url.hostname)) {
    e.respondWith((async () => {
      const hit = await caches.match(req);
      if (hit) return hit;
      try { return putCopy(FONTS, req, await fetch(req)); }
      catch (err) { return new Response('', {status: 504}); }
    })());
  }
});
