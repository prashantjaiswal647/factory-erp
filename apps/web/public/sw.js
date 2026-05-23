// Munshi AI ERP PWA Service Worker
const CACHE_NAME = "munshi-ai-erp-v1";

self.addEventListener("install", (event) => {
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener("fetch", (event) => {
  const url = event.request.url;

  // Rigid interceptor filter block: Bypass Service Worker completely for backend API endpoints and templates.
  // Return early without calling event.respondWith() so the browser handles these fetches natively via the standard network stack.
  if (url.includes("/api/") || url.includes("/templates")) {
    return;
  }

  // Default network pass-through for other assets to keep operation simple and crash-free
  event.respondWith(fetch(event.request));
});
