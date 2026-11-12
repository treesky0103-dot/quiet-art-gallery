/* Service worker caches only app shell, never third-party images. Native APK uses its own bounded LRU. */
const SHELL='quiet-gallery-shell-v12';
const FILES=['./','./index.html','./style.css','./core.js','./app.js','./manifest.webmanifest','./icon-192.png','./icon-512.png'];
self.addEventListener('install',e=>e.waitUntil(caches.open(SHELL).then(c=>c.addAll(FILES)).then(()=>self.skipWaiting())));
self.addEventListener('activate',e=>e.waitUntil(caches.keys().then(names=>Promise.all(names.filter(x=>x!==SHELL).map(x=>caches.delete(x)))).then(()=>self.clients.claim())));
self.addEventListener('fetch',e=>{
  const u=new URL(e.request.url);
  if(u.origin!==self.location.origin||e.request.method!=='GET')return;
  e.respondWith(caches.match(e.request).then(v=>v||fetch(e.request)));
});
