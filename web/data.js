// All network access lives here. P6b swaps the fixture branch for the live API.
// ?fixture=1 (or empty | limited | error) loads synthetic files from tests/fixtures/; &delay=ms slows them down.
var Data = (function () {
  var q = new URLSearchParams(location.search);
  var fx = q.get('fixture');
  var delay = +q.get('delay') || 0;
  var FX = '../tests/fixtures/';
  var files = {'1': 'journeys.sample.json', empty: 'ui_journeys_empty.json', limited: 'ui_journeys_limited.json'};

  function get(url) {
    return fetch(url, {headers: {Accept: 'application/json'}}).then(function (r) {
      if (!r.ok) throw new Error(r.status + ' ' + url);
      return r.json();
    });
  }

  function later(f) {
    return new Promise(function (ok) { setTimeout(ok, delay); }).then(f);
  }

  return {
    fixture: fx,
    stops: function () {
      return later(function () { return get(fx ? FX + 'ui_stops.json' : '/stops/all'); });
    },
    // r: {from, to, depart: 'YYYY-MM-DDTHH:MM', daytype, pref}
    journeys: function (r) {
      if (fx === 'error') return later(function () { throw new Error('fixture error'); });
      if (fx) return later(function () { return get(FX + (files[fx] || files['1'])); });
      return get('/journeys?' + new URLSearchParams(r));
    }
  };
})();
