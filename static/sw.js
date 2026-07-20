const CACHE_NAME = "lv-pwa-v6";
const DB_NAME = "lv-offline";
const QUEUE_STORE = "queue";
const STATIC_ASSETS = [
  "/",
  "/manifest.json",
  "/offline.html",
  "/icons/icon.svg",
  "/icons/icon-192.png",
  "/icons/icon-512.png",
  "/icons/icon-maskable.png"
];

self.addEventListener("install", event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(STATIC_ASSETS))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(key => key !== CACHE_NAME).map(key => caches.delete(key))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", event => {
  const url = new URL(event.request.url);
  if (url.origin !== location.origin) return;

  if (url.pathname === "/api/query" && event.request.method === "POST") {
    event.respondWith(networkOrQueue(event.request));
    return;
  }

  if (url.pathname.startsWith("/api/") || url.pathname === "/ws") {
    event.respondWith(fetch(event.request));
    return;
  }

  if (url.pathname.startsWith("/icons/") || url.pathname === "/manifest.json") {
    event.respondWith(cacheFirst(event.request));
    return;
  }

  event.respondWith(networkFirst(event.request));
});

self.addEventListener("sync", event => {
  if (event.tag === "lv-replay-queue") {
    event.waitUntil(replayQueue());
  }
});

self.addEventListener("message", event => {
  if (event.data && event.data.type === "LV_ONLINE") {
    event.waitUntil(replayQueue());
  }
  if (event.data && event.data.type === "LV_QUEUE_STATUS") {
    event.waitUntil(queueSize().then(count => event.source?.postMessage({ type: "LV_QUEUE_STATUS", count })));
  }
  if (event.data && event.data.type === "LV_REPLAY_NOW") {
    event.waitUntil(replayQueue());
  }
  if (event.data && event.data.type === "LV_CLEAR_QUEUE") {
    event.waitUntil(clearQueued().then(() => notifyClients({ type: "LV_QUEUE_CLEARED", count: 0 })));
  }
});

async function networkOrQueue(request) {
  const body = await request.clone().json().catch(() => ({}));
  try {
    return await fetch(request);
  } catch (error) {
    const entry = {
      id: makeId(),
      created_at: new Date().toISOString(),
      url: request.url,
      method: request.method,
      body: stripPiiFromBody(body),  // PII stripped before disk write
      status: "queued"
    };
    await enqueue(entry);
    await registerReplay();
    const count = await queueSize();
    notifyClients({ type: "LV_QUEUED", entry, count });
    return jsonResponse({
      type: "queued",
      queued: true,
      queue_count: count,
      message: "Queued locally. It will run through governance when connection returns."
    }, 202);
  }
}

function makeId() {
  if (crypto.randomUUID) return crypto.randomUUID();
  return `queued-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

async function replayQueue() {
  const entries = await allQueued();
  if (!entries.length) return;
  notifyClients({ type: "LV_REPLAY_START", count: entries.length });

  for (const entry of entries) {
    try {
      const response = await fetch("/api/query", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-LV-Replayed": "1" },
        body: JSON.stringify(entry.body)
      });
      const payload = await response.json().catch(() => ({}));
      await removeQueued(entry.id);
      notifyClients({ type: "LV_REPLAYED", entry, response: payload, remaining: await queueSize() });
    } catch (error) {
      notifyClients({ type: "LV_REPLAY_PAUSED", error: String(error), remaining: await queueSize() });
      return;
    }
  }
}

async function cacheFirst(request) {
  const cached = await caches.match(request);
  if (cached) return cached;
  const response = await fetch(request);
  const cache = await caches.open(CACHE_NAME);
  cache.put(request, response.clone());
  return response;
}

async function networkFirst(request) {
  try {
    const response = await fetch(request);
    const cache = await caches.open(CACHE_NAME);
    if (request.method === "GET") cache.put(request, response.clone());
    return response;
  } catch (error) {
    return await caches.match(request) || await caches.match("/offline.html");
  }
}

function jsonResponse(payload, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json", "X-LV-Offline-Queue": "1" }
  });
}

function notifyClients(message) {
  self.clients.matchAll({ includeUncontrolled: true }).then(clients => {
    clients.forEach(client => client.postMessage(message));
  });
}

function openDb() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, 1);
    req.onupgradeneeded = () => req.result.createObjectStore(QUEUE_STORE, { keyPath: "id" });
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function txStore(mode) {
  const db = await openDb();
  return db.transaction(QUEUE_STORE, mode).objectStore(QUEUE_STORE);
}

async function enqueue(entry) {
  const store = await txStore("readwrite");
  return requestDone(store.put(entry));
}

async function allQueued() {
  const store = await txStore("readonly");
  return requestDone(store.getAll()).then(entries => entries.sort((a, b) => a.created_at.localeCompare(b.created_at)));
}

async function removeQueued(id) {
  const store = await txStore("readwrite");
  return requestDone(store.delete(id));
}

async function clearQueued() {
  const store = await txStore("readwrite");
  return requestDone(store.clear());
}

async function queueSize() {
  const store = await txStore("readonly");
  return requestDone(store.count());
}

function requestDone(req) {
  return new Promise((resolve, reject) => {
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

// ── Offline PII Protection ──────────────────────────────────────
// Before writing to IndexedDB, strip PII patterns client-side.
// This prevents sensitive data from persisting on disk unprotected.
// The full sanitizer runs server-side on replay; this is defense-in-depth.

const PII_PATTERNS = [
  { name: "ssn", re: /\b\d{3}-\d{2}-\d{4}\b/g },
  { name: "ssn_nodash", re: /\b\d{9}\b/g },
  { name: "email", re: /\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b/g },
  { name: "phone_us", re: /\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b/g },
  { name: "phone_intl", re: /\b\+\d{1,3}[-.\s]?\d{6,14}\b/g },
  { name: "credit_card", re: /\b(?:\d[ -]*?){13,19}\b/g },
  { name: "dob", re: /\b(?:born|DOB|date of birth)[:\s]*\d{1,2}[\/.-]\d{1,2}[\/.-]\d{2,4}\b/gi },
  { name: "passport", re: /\b[A-Z]{1,2}\d{6,9}\b/g },
  { name: "mrn", re: /\b(?:MRN|mrn)[:\s#]?\d{4,}\b/gi },
  { name: "address", re: /\b\d{1,5}\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s+(?:Street|St|Avenue|Ave|Road|Rd|Drive|Dr|Lane|Ln|Boulevard|Blvd|Way|Court|Ct)\b/gi },
];

function stripPiiFromBody(body) {
  if (!body || typeof body !== "object") return body;
  const cleaned = JSON.parse(JSON.stringify(body));
  for (const key of Object.keys(cleaned)) {
    if (typeof cleaned[key] === "string") {
      for (const pat of PII_PATTERNS) {
        cleaned[key] = cleaned[key].replace(pat.re, `[QUEUED_${pat.name.toUpperCase()}]`);
      }
    }
  }
  return cleaned;
}

async function registerReplay() {
  if ("sync" in self.registration) {
    await self.registration.sync.register("lv-replay-queue");
  }
}
