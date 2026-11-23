// All network access lives here. The live API is the default.
// ?fixture=1 (or empty | limited | error) swaps stops and journeys for synthetic files in tests/fixtures/
// (serve the repo root for that); &delay=ms slows any call down.
// Errors reject with e.code: the API's detail.code (same_stop, outside_area, unknown_stop, bad_depart,
// invalid_input), 'http' for other bad statuses, 'network' when the request never got a reply.
var Data = (function () {
  var q = new URLSearchParams(location.search);
  var fx = q.get('fixture');
  var delay = +q.get('delay') || 0;
  var FX = '../tests/fixtures/';
  var files = {'1': 'journeys.sample.json', empty: 'ui_journeys_empty.json', limited: 'ui_journeys_limited.json'};
  var cache = {};

  function fail(code, msg) { var e = new Error(msg || code); e.code = code; return e; }

  function get(url) {
    return fetch(url, {headers: {Accept: 'application/json'}}).then(function (r) {
      if (r.ok) return r.json();
      return r.json().catch(function () { return {}; }).then(function (b) {
        var d = (b && b.detail) || {};
        throw fail(d.code || 'http', d.message || r.status + ' ' + url);
      });
    }, function () { throw fail('network'); });
  }

  function later(f) {
    return new Promise(function (ok) { setTimeout(ok, delay); }).then(f);
  }

  // Cached GETs for the read-only operator and data endpoints; a failed call is not cached.
  function once(url) {
    if (!cache[url]) cache[url] = later(function () { return get(url); }).catch(function (e) { delete cache[url]; throw e; });
    return cache[url];
  }

  function qs(o) { return new URLSearchParams(o).toString(); }

  return {
    fixture: fx,
    stops: function () {
      return later(function () { return get(fx ? FX + 'ui_stops.json' : '/stops/all'); });
    },
    // r: {from, to, depart: 'YYYY-MM-DDTHH:MM', daytype, pref}
    journeys: function (r) {
      if (fx === 'error') return later(function () { throw fail('network'); });
      if (fx) return later(function () { return get(FX + (files[fx] || files['1'])); });
      return later(function () { return get('/journeys?' + qs(r)); });
    },
    heatmap: function (daytype, hour) { return once('/crowding/heatmap?' + qs({daytype: daytype, hour: hour})); },
    top: function (daytype, period) {
      return once('/operator/top?' + qs({daytype: daytype, period: period})).then(function (b) { return (b && b.rows) || []; });
    },
    route: function (base, dir, daytype, time) {
      return once('/crowding/route/' + encodeURIComponent(base) + '/' + encodeURIComponent(dir) + '?' + qs({daytype: daytype, time: time}));
    },
    coverage: function () { return once('/coverage'); }
  };
})();
