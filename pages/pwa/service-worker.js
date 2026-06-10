const CACHE_NAME = "pocket-store-pwa-v1";
const IMAGE_CACHE_NAME = "pocket-store-pwa-images-v1";
const PRECACHE_URLS = [
  "/pwa/",
  "/pwa/app.css",
  "/pwa/app.js",
  "/pwa/manifest.webmanifest",
  "/pwa/offline.html",
  "/pwa/catalog.json",
  "/pwa/cart-index.json",
  "/pwa/icons/icon-192.svg",
  "/pwa/icons/icon-512.svg",
  "/store/catalog.json",
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(PRECACHE_URLS)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))))
  );
  self.clients.claim();
});

async function staleWhileRevalidate(request) {
  const cache = await caches.open(CACHE_NAME);
  const cached = await cache.match(request);
  const networkPromise = fetch(request)
    .then((response) => {
      if (response && response.ok) cache.put(request, response.clone());
      return response;
    })
    .catch(() => cached);
  return cached || networkPromise;
}

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return;
  const url = new URL(request.url);

  if (request.destination === "image") {
    event.respondWith(
      caches.open(IMAGE_CACHE_NAME).then(async (cache) => {
        const cached = await cache.match(request);
        if (cached) return cached;
        try {
          const response = await fetch(request);
          if (response && response.ok) cache.put(request, response.clone());
          return response;
        } catch {
          return cached || Response.error();
        }
      })
    );
    return;
  }

  if (url.origin !== self.location.origin) return;

  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request)
        .then((response) => response)
        .catch(async () => (await caches.match("/pwa/offline.html")) || Response.error())
    );
    return;
  }

  if (url.pathname.startsWith("/pwa/") || url.pathname === "/store/catalog.json") {
    event.respondWith(staleWhileRevalidate(request));
  }
});
