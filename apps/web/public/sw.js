// Munshi AI ERP service worker cleanup shim.
// Dynamic authenticated API traffic must never be handled by a service worker.
const CACHE_NAME = "munshi-ai-erp-disabled-v2";

self.addEventListener("install", (event) => {
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.map((key) => caches.delete(key))))
      .then(() => self.registration.unregister())
      .then(() => self.clients.matchAll({ type: "window" }))
      .then((clients) => {
        clients.forEach((client) => client.navigate(client.url));
      })
  );
});

self.addEventListener("fetch", (event) => {
  // Network-only gateway: no runtime cache strategy may handle data entry,
  // manufacturing summaries, auth, billing, onboarding, inventory, production,
  // sales, expenses, templates, or any backend REST endpoint.
  if (event.request.url.includes("/api/")) {
    // Bypasses service worker caching for all dynamic backend REST queries.
    event.respondWith(fetch(event.request));
    return;
  }

  if (event.request.url.includes("/templates")) {
    event.respondWith(fetch(event.request));
    return;
  }

  event.respondWith(fetch(event.request));
});
