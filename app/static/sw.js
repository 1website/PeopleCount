const CACHE_NAME = "cambodia-census-v1";
const ASSETS_TO_CACHE = [
  "/",
  "/static/css/style.css",
  "/static/css/print.css",
  "/static/js/db.js",
  "/static/js/sync.js",
  "/static/js/app.js",
  "/static/manifest.json",
  "/static/icons/icon-192.svg",
  "/static/icons/icon-512.svg"
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      console.log("[Service Worker] Caching app shell and static assets");
      return cache.addAll(ASSETS_TO_CACHE);
    })
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.map((key) => {
          if (key !== CACHE_NAME) {
            console.log("[Service Worker] Removing old cache:", key);
            return caches.delete(key);
          }
        })
      );
    })
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  // If requesting API endpoint, network first or handle offline in app code
  if (event.request.url.includes("/api/")) {
    return;
  }

  event.respondWith(
    caches.match(event.request).then((cachedResponse) => {
      if (cachedResponse) {
        return cachedResponse;
      }
      return fetch(event.request).catch(() => {
        // Fallback to offline index if html request
        if (event.request.headers.get("accept")?.includes("text/html")) {
          return caches.match("/");
        }
      });
    })
  );
});
