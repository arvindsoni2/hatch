// Service worker kill-switch: immediately unregisters itself.
// Prior versions cached /api/async-jobs polling requests (unique since= params)
// which exhausted Chrome's Cache API quota -> "insufficient resources" / blank page.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.map((k) => caches.delete(k))))
      .then(() => self.registration.unregister())
  );
});
