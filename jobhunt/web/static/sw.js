// jobhunt service worker: push notifications only. No offline caching (pages must always be fresh).
self.addEventListener('install', function () { self.skipWaiting(); });
self.addEventListener('activate', function (e) { e.waitUntil(self.clients.claim()); });

self.addEventListener('push', function (e) {
  var data = {};
  try { data = e.data ? e.data.json() : {}; } catch (err) { data = { title: 'jobhunt', body: e.data ? e.data.text() : '' }; }
  var opts = {
    body: data.body || '',
    icon: '/static/icons/icon-192.png',
    badge: '/static/icons/icon-192.png',
    tag: data.tag || 'jobhunt',
    renotify: !!data.renotify,
    requireInteraction: !!data.urgent,
    data: { url: data.url || '/', key: data.key || '' },
    actions: data.key ? [{ action: 'open', title: data.action || 'Open' }, { action: 'snooze', title: 'Snooze 1 h' }] : []
  };
  e.waitUntil(self.registration.showNotification(data.title || 'jobhunt', opts));
});

self.addEventListener('notificationclick', function (e) {
  e.notification.close();
  var d = e.notification.data || {};
  if (e.action === 'snooze' && d.key) {
    e.waitUntil(fetch('/push/snooze', { method: 'POST', credentials: 'include',
      headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ key: d.key, hours: 1 }) }).catch(function () {}));
    return;
  }
  var url = d.url || '/';
  e.waitUntil(self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function (list) {
    for (var i = 0; i < list.length; i++) {
      if ('focus' in list[i]) { list[i].navigate(url); return list[i].focus(); }
    }
    return self.clients.openWindow(url);
  }));
});
