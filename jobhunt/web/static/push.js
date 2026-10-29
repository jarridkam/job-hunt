// Phone alerts: register the service worker, and let the user turn Web Push on/off.
// Shows the "Turn on alerts" card on Today only where push can work (secure context, supported, not yet on).
(function () {
  var supported = 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window && window.isSecureContext;
  var ios = /iPhone|iPad|iPod/.test(navigator.userAgent) || (/Macintosh/.test(navigator.userAgent) && (navigator.maxTouchPoints || 0) > 1);
  var standalone = window.matchMedia('(display-mode: standalone)').matches || navigator.standalone === true;

  function b64ToBytes(s) {
    var pad = '='.repeat((4 - s.length % 4) % 4);
    var raw = atob((s + pad).replace(/-/g, '+').replace(/_/g, '/'));
    var out = new Uint8Array(raw.length);
    for (var i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i);
    return out;
  }
  function post(url, body) {
    return fetch(url, { method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
      .then(function (r) { return r.json(); });
  }
  function toast(msg) { if (window.showToast) window.showToast(msg, 6000); else console.log(msg); }

  var regP = supported ? navigator.serviceWorker.register('/sw.js', { scope: '/' }).catch(function (e) { console.warn('sw', e); return null; }) : Promise.resolve(null);

  window.jobhuntPush = {
    supported: supported,
    status: function () {
      return regP.then(function (reg) { return reg ? reg.pushManager.getSubscription() : null; })
        .then(function (sub) { return { on: !!sub, sub: sub }; });
    },
    enable: function () {
      if (!supported) {
        if (ios && !standalone) return Promise.reject(new Error('On iPhone, first add jobhunt to your Home Screen (Share → Add to Home Screen), then open it from there.'));
        return Promise.reject(new Error('This browser cannot receive push alerts here. Use the ntfy option in Settings instead.'));
      }
      return Notification.requestPermission().then(function (perm) {
        if (perm !== 'granted') throw new Error('Alerts are blocked for this site. Allow notifications in the browser settings and try again.');
        return Promise.all([regP, fetch('/push/state', { credentials: 'include' }).then(function (r) { return r.json(); })]);
      }).then(function (res) {
        var reg = res[0], state = res[1];
        if (!reg) throw new Error('Service worker did not register.');
        return reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: b64ToBytes(state.vapid_public) });
      }).then(function (sub) {
        var label = (ios ? 'iPhone' : /Android/.test(navigator.userAgent) ? 'Android' : 'Desktop') + ' · ' + (standalone ? 'app' : 'browser');
        return post('/push/subscribe', { subscription: sub.toJSON(), label: label });
      });
    },
    disable: function () {
      return regP.then(function (reg) { return reg ? reg.pushManager.getSubscription() : null; }).then(function (sub) {
        if (!sub) return { ok: true };
        var ep = sub.endpoint;
        return sub.unsubscribe().then(function () { return post('/push/unsubscribe', { endpoint: ep }); });
      });
    }
  };

  function wire() {
    var card = document.getElementById('push-card');
    var btn = document.getElementById('push-enable');
    var hint = document.getElementById('push-hint');
    var dismissed = false;
    try { dismissed = localStorage.getItem('jobhunt.push.dismissed') === '1'; } catch (e) {}
    if (card && btn && !dismissed) {
      var canTry = supported || (ios && !standalone);
      window.jobhuntPush.status().then(function (s) {
        if (!s.on && canTry) {
          if (ios && !standalone && hint) hint.textContent = 'On iPhone: Share → Add to Home Screen, open it from there, then tap this.';
          card.hidden = false;
        }
      });
      btn.addEventListener('click', function () {
        btn.disabled = true;
        window.jobhuntPush.enable().then(function () {
          toast('Alerts on. You will get a test push in a moment.');
          card.hidden = true;
          return fetch('/push/test', { method: 'POST', credentials: 'include' });
        }).catch(function (e) { toast(e.message || String(e)); btn.disabled = false; });
      });
      var x = document.createElement('button');
      x.type = 'button'; x.className = 'small'; x.textContent = 'Not now';
      x.addEventListener('click', function () { card.hidden = true; try { localStorage.setItem('jobhunt.push.dismissed', '1'); } catch (e) {} });
      btn.insertAdjacentElement('afterend', x);
    }
    // Settings page controls
    var on = document.getElementById('push-on'), off = document.getElementById('push-off'), st = document.getElementById('push-this-device');
    if (st) {
      window.jobhuntPush.status().then(function (s) {
        st.textContent = s.on ? 'This device: alerts on.' : supported ? 'This device: alerts off.' : (ios && !standalone) ? 'iPhone: add to Home Screen first, then open from there.' : 'This browser cannot receive pushes (needs HTTPS or localhost).';
        if (on) on.hidden = s.on; if (off) off.hidden = !s.on;
      });
      if (on) on.addEventListener('click', function () { window.jobhuntPush.enable().then(function () { location.reload(); }).catch(function (e) { toast(e.message || String(e)); }); });
      if (off) off.addEventListener('click', function () { window.jobhuntPush.disable().then(function () { location.reload(); }); });
    }
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', wire); else wire();
})();
