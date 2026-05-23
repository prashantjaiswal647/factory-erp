// Munshi AI ERP PWA Service Worker
const CACHE_NAME = "munshi-ai-erp-v1";

self.addEventListener("install", (event) => {
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener("fetch", (event) => {
  // Rigid interceptor filter block at the absolute top of the Fetch event listener hook:
  if (event.request.url.includes('/api/')) {
    event.respondWith(fetch(event.request)); // Force absolute immediate clean network request pass-through
    return;
  }

  // Default network pass-through for other assets to keep operation simple and crash-free
  event.respondWith(fetch(event.request));
});
