/* 极简 Service Worker：网络优先，离线时回退缓存/离线页（不缓存动态内容，避免读到旧数据） */
const CACHE = "ai-news-shell-v1";
const PRECACHE = ["/offline.html", "/manifest.json", "/static/icons/icon-192.png"];

self.addEventListener("install", (e) => {
  e.waitUntil(
    caches.open(CACHE).then((c) => c.addAll(PRECACHE)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  if (e.request.method !== "GET") return;
  const url = new URL(e.request.url);
  if (url.pathname.startsWith("/api/")) return; // API 永远走网络
  e.respondWith(
    fetch(e.request).catch(() =>
      caches.match(e.request).then(
        (hit) => hit || (e.request.mode === "navigate" ? caches.match("/offline.html") : Response.error())
      )
    )
  );
});
