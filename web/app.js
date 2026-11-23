(function () {
  'use strict';

  var RANK = ['MANY_SEATS_AVAILABLE', 'FEW_SEATS_AVAILABLE', 'STANDING_ROOM_ONLY', 'CRUSHED_STANDING_ROOM_ONLY'];
  var ICON = {MANY_SEATS_AVAILABLE: 'seat2', FEW_SEATS_AVAILABLE: 'seat1', STANDING_ROOM_ONLY: 'stand', CRUSHED_STANDING_ROOM_ONLY: 'crowd', NO_DATA_AVAILABLE: 'nodata'};
  var ND = 'NO_DATA_AVAILABLE';
  var DEFAULT = {from: 'anand vihar', to: 'connaught place', daytype: 'weekday', time: '18:00'};

  var s = {stops: [], box: null, from: null, to: null, daytype: DEFAULT.daytype, time: DEFAULT.time,
           pref: 'fastest', res: null, sel: null, status: 'idle', picking: null, seq: 0};
  var map = null, mapReady = false, popup = null;

  function $(q, el) { return (el || document).querySelector(q); }
  function $$(q, el) { return Array.prototype.slice.call((el || document).querySelectorAll(q)); }
  function esc(x) {
    return String(x == null ? '' : x).replace(/[&<>"']/g, function (c) {
      return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c];
    });
  }
  function stop(n) { return '<span lang="en">' + esc(n) + '</span>'; }
  function icon(n) { return '<svg class="ic" aria-hidden="true"><use href="#i-' + n + '"/></svg>'; }
  function rank(l) { return RANK.indexOf(l); }
  function lv(l) { var r = rank(l); return r < 0 ? 0 : r + 1; }
  function kOf(p) { return p == null ? null : Math.round(p * 10); }
  function mins(hhmm) { var p = String(hhmm || '0:0').split(':'); return +p[0] * 60 + +p[1]; }
  function hhmm(m) { m = ((m % 1440) + 1440) % 1440; return String(Math.floor(m / 60)).padStart(2, '0') + ':' + String(m % 60).padStart(2, '0'); }
  function store(k, v) { try { if (v === undefined) return localStorage.getItem(k); localStorage.setItem(k, v); } catch (e) { return null; } }

  function chip(level, small) {
    level = level || ND;
    return '<span class="chip lv-' + lv(level) + (small ? ' sm' : '') + '">' + icon(ICON[level] || 'nodata') +
      '<span>' + esc(t('short.' + level)) + '</span></span>';
  }

  // ---------- stop search ----------
  function norm(x) { return String(x).toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim(); }

  function setStops(list) {
    s.stops = (list || []).filter(function (x) { return x && x.name; }).map(function (x) {
      return {stop_id: x.stop_id, name: x.name, lat: +x.lat, lon: +x.lon, n: norm(x.name), tk: norm(x.name).split(' ')};
    });
    var lat = s.stops.map(function (x) { return x.lat; }), lon = s.stops.map(function (x) { return x.lon; });
    s.box = s.stops.length ? [Math.min.apply(0, lon), Math.min.apply(0, lat), Math.max.apply(0, lon), Math.max.apply(0, lat)] : null;
  }

  function find(q, max) {
    var qn = norm(q), qt = qn ? qn.split(' ') : [];
    if (!qt.length) return [];
    var hits = [];
    s.stops.forEach(function (x) {
      var sc = x.n.indexOf(qn) === 0 ? 0 : qt.every(function (w) { return x.tk.some(function (k) { return k.indexOf(w) === 0; }); }) ? 1 : -1;
      if (sc >= 0) hits.push([sc, x]);
    });
    hits.sort(function (a, b) { return a[0] - b[0] || a[1].name.length - b[1].name.length; });
    return hits.slice(0, max || 8).map(function (h) { return h[1]; });
  }

  function combo(field) {
    var inp = $('#' + field), box = $('#' + field + '-list'), hits = [], act = -1;

    function close() { box.hidden = true; inp.setAttribute('aria-expanded', 'false'); inp.removeAttribute('aria-activedescendant'); act = -1; }
    function mark() {
      $$('li', box).forEach(function (li, i) { li.setAttribute('aria-selected', i === act ? 'true' : 'false'); });
      if (act >= 0) { inp.setAttribute('aria-activedescendant', field + '-opt-' + act); $('#' + field + '-opt-' + act).scrollIntoView({block: 'nearest'}); }
      else inp.removeAttribute('aria-activedescendant');
    }
    function open() {
      hits = find(inp.value);
      act = -1;
      box.innerHTML = hits.length ? hits.map(function (x, i) {
        return '<li role="option" id="' + field + '-opt-' + i + '" aria-selected="false" lang="en">' + esc(x.name) + '</li>';
      }).join('') : (inp.value.trim() ? '<li class="none" role="option" aria-disabled="true" aria-selected="false">' + esc(t('stop.none', {q: inp.value.trim()})) + '</li>' : '');
      box.hidden = !box.innerHTML;
      inp.setAttribute('aria-expanded', box.hidden ? 'false' : 'true');
      mark();
    }
    function pick(i) { if (hits[i]) { setField(field, hits[i]); close(); } }

    inp.addEventListener('input', function () {
      var hit = s.stops.filter(function (x) { return x.n === norm(inp.value); })[0];
      s[field] = hit || null;
      open();
    });
    inp.addEventListener('keydown', function (e) {
      var n = hits.length;
      if (e.key === 'ArrowDown') { e.preventDefault(); if (box.hidden) open(); act = n ? (act + 1) % n : -1; mark(); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); if (box.hidden) open(); act = n ? (act <= 0 ? n - 1 : act - 1) : -1; mark(); }
      else if (e.key === 'Enter' && !box.hidden && act >= 0) { e.preventDefault(); pick(act); }
      else if (e.key === 'Escape') { if (!box.hidden) { e.preventDefault(); close(); } }
      else if (e.key === 'Tab') close();
    });
    inp.addEventListener('blur', close);
    box.addEventListener('mousedown', function (e) {
      e.preventDefault();
      var li = e.target.closest('li[role="option"]');
      if (li) pick($$('li[role="option"]', box).indexOf(li));
    });
  }

  function setField(field, x) {
    s[field] = x;
    $('#' + field).value = x ? x.name : '';
    $('#' + field).removeAttribute('aria-invalid');
    $('#form-msg').textContent = '';
  }

  // ---------- search ----------
  function today() {
    var d = new Date();
    return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
  }

  function check() {
    if (!s.from) return ['from', t('err.need_stop', {field: t('from')})];
    if (!s.to) return ['to', t('err.need_stop', {field: t('to')})];
    if (s.from === s.to || (s.from.stop_id != null && s.from.stop_id === s.to.stop_id)) return ['to', t('err.same')];
    return null;
  }

  function search() {
    var bad = check();
    if (bad) { showForm(true); $('#form-msg').textContent = bad[1]; $('#' + bad[0]).setAttribute('aria-invalid', 'true'); $('#' + bad[0]).focus(); return; }
    s.status = 'loading';
    s.res = null;
    s.err = '';
    var n = ++s.seq;
    showForm(false);
    render();
    Data.journeys({from: s.from.stop_id, to: s.to.stop_id, depart: today() + 'T' + s.time, daytype: s.daytype, pref: s.pref})
      .then(function (r) {
        if (n !== s.seq) return;
        s.res = r || {};
        var o = sorted();
        s.status = o.length ? 'ok' : 'empty';
        s.sel = o.length ? o[0].id : null;
        render();
        draw();
      }, function () {
        if (n !== s.seq) return;
        s.status = 'error';
        render();
        draw();
      });
  }

  function boot() {
    s.status = 'loading';
    render();
    Data.stops().then(function (list) {
      setStops(list);
      setField('from', find(DEFAULT.from, 1)[0] || null);
      setField('to', find(DEFAULT.to, 1)[0] || null);
      if (s.from && s.to) search(); else { s.status = 'idle'; render(); showForm(true); }
    }, function () {
      s.status = 'error';
      s.err = 'stops';
      render();
    });
  }

  function showForm(on) {
    $('#form').hidden = !on;
    $('#enquiry').hidden = on || !s.from || !s.to;
    enquiry();
  }

  function enquiry() {
    if (!s.from || !s.to) return;
    $('#enq-od').innerHTML = stop(s.from.name) + ' → ' + stop(s.to.name);
    $('#enq-when').textContent = t('daytype.' + s.daytype) + ' ∙ ' + s.time;
  }

  // ---------- options ----------
  function ids(o) { o.forEach(function (x, i) { if (x.id == null) x.id = 'opt' + i; }); return o; }

  function sorted() {
    var o = ids(((s.res && s.res.options) || []).slice()), q = mins(s.time);
    function arr(x) { var a = mins(x.arrive); return a < q - 360 ? a + 1440 : a; }
    o.sort(s.pref === 'comfort'
      ? function (a, b) { return (a.generalised_min == null ? 1e9 : a.generalised_min) - (b.generalised_min == null ? 1e9 : b.generalised_min) || arr(a) - arr(b); }
      : function (a, b) { return arr(a) - arr(b) || a.total_min - b.total_min; });
    return o;
  }

  function buses(o) { return (o.legs || []).filter(function (l) { return l.mode === 'bus'; }); }

  // Option-level summary: worst leg level and lowest seat chance. Any leg without data makes the option limited.
  function summary(o) {
    if (o.crowding) return o.crowding;
    var b = buses(o), c = b.map(function (l) { return l.crowding || {level: ND}; });
    var nd = !c.length || c.some(function (x) { return !x.level || x.level === ND; });
    var worst = nd ? ND : c.reduce(function (a, x) { return rank(x.level) > rank(a.level) ? x : a; }).level;
    var ps = c.map(function (x) { return x.p_seat; }).filter(function (p) { return p != null; });
    var conf = ['low', 'medium', 'high'].filter(function (k) { return c.some(function (x) { return x.confidence === k; }); })[0];
    var ns = c.map(function (x) { return x.n; }).filter(function (n) { return n != null; });
    return {level: worst, p_seat: nd || !ps.length ? null : Math.min.apply(0, ps), confidence: conf,
            n: ns.length ? Math.min.apply(0, ns) : null, reason: (c.filter(function (x) { return x.reason; })[0] || {}).reason};
  }

  function runs(segs) {
    var out = [], cur = null;
    segs.forEach(function (g, i) {
      if (rank(g.level) >= 2) { if (cur) cur.b = i; else cur = {a: i, b: i}; }
      else if (cur) { out.push(cur); cur = null; }
    });
    if (cur) out.push(cur);
    return out;
  }

  function stripText(segs) {
    var nd = segs.filter(function (g) { return g.level === ND; }).length;
    if (!segs.length || nd === segs.length) return t('strip.none');
    var r = runs(segs);
    if (!r.length) return t(nd ? 'strip.partial' : 'strip.calm');
    var s = r.map(function (x, i) {
      var a = segs[x.a].from, b = segs[x.b].to;
      // claim "seats until a" only when every stretch before the crowding has data
      return i === 0 && x.a > 0 && !nd ? t('strip.until', {a: a, b: b}) : t('strip.from', {a: a, b: b});
    }).join('; ');
    return nd ? s + '; ' + t('strip.some_nd') : s;
  }

  function strip(leg) {
    var segs = leg.segments && leg.segments.length ? leg.segments
      : [{from: leg.board, to: leg.alight, min: leg.ride_min || 1, level: (leg.crowding || {}).level || ND}];
    var cols = segs.map(function (g) { return 'minmax(6px, ' + Math.max(+g.min || 1, 1) + 'fr)'; }).join(' ');
    var cells = segs.map(function (g, i) {
      var tip = t('strip.cell', {a: g.from, b: g.to, level: t('level.' + (g.level || ND)), m: g.min});
      return '<span class="cell lv-' + lv(g.level) + '" style="grid-column:' + (i + 1) + '" title="' + esc(tip) + '"></span>';
    }).join('');
    var marks = runs(segs).map(function (x) { return '<span class="run" style="grid-column:' + (x.a + 1) + ' / ' + (x.b + 2) + '"></span>'; }).join('');
    var txt = stripText(segs);
    return '<div class="strip-wrap"><div class="strip" role="img" aria-label="' + esc(t('strip.label', {s: txt})) +
      '" style="grid-template-columns:' + cols + '">' + cells + marks + '</div></div>' +
      '<p class="strip-text" aria-hidden="true">' + esc(txt) + '</p>';
  }

  function crowdLine(o, c) {
    var parts = [];
    if (c.level !== ND && c.p_seat != null) parts.push(esc(t('seats_k_of_10', {k: kOf(c.p_seat)})));
    if (c.level === ND) parts.push(esc(t('level.' + ND)));
    buses(o).forEach(function (l) {
      var cb = l.crowding && l.crowding.crowded_between;
      if (cb && cb.length === 2) parts.push(t('crowded_between', {a: stop(cb[0]), b: stop(cb[1])}));
    });
    return parts.join(' ∙ ');
  }

  function legHtml(l, i, legs) {
    if (l.mode === 'walk') {
      var dest = l.to === 'destination' || i === legs.length - 1;
      var key = dest ? 'walk.dest' : (i > 0 ? 'walk.transfer' : 'walk.to');
      return '<li class="leg walk">' + icon('walk') + '<span>' + t(key, {m: esc(l.min), stop: stop(l.to)}) + '</span></li>';
    }
    var c = l.crowding || {level: ND}, k = c.level === ND ? null : kOf(c.p_seat);
    return '<li class="leg bus">' + icon('bus') + '<div>' +
      '<div class="leg-head"><span class="route" lang="en">' + esc(l.route) + '</span>' +
      (l.headsign ? '<span class="towards">' + t('bus.towards', {h: stop(l.headsign)}) + '</span>' : '') +
      chip(c.level, true) + (k != null ? '<span class="k">' + esc(t('avail.k', {k: k})) + '</span>' : '') +
      (l.ride_min != null ? '<span class="ride">' + esc(t('bus.ride', {m: l.ride_min})) + '</span>' : '') + '</div>' +
      '<p class="stopline">' + t('bus.board', {t: '<b class="tnum">' + esc(l.depart) + '</b>', stop: stop(l.board)}) + '</p>' +
      strip(l) +
      '<p class="stopline">' + (l.arrive ? t('bus.alight', {t: '<b class="tnum">' + esc(l.arrive) + '</b>', stop: stop(l.alight)}) : t('bus.alight_notime', {stop: stop(l.alight)})) + '</p>' +
      '</div></li>';
  }

  function suggestions(o, list) {
    var mine = (s.res.suggestions || []).filter(function (g) {
      return g.for ? g.for === o.id : (o.label === 'fastest' || list[0] === o);
    });
    if (!mine.length) return '';
    return '<ul class="sugg">' + mine.map(function (g) {
      var k = kOf(g.p_seat);
      if (g.type === 'leave_later') {
        return '<li>' + icon('clock') + '<span><b>' + esc(t('leave_later', {t: g.depart})) + '</b> <span class="more">' +
          esc(t('leave_later.more', {k: k, m: g.extra_min})) + '</span></span></li>';
      }
      if (g.type === 'board_upstream') {
        return '<li>' + icon('walk') + '<span><b>' + t('board_upstream', {m: esc(g.walk_min), stop: stop(g.stop)}) + '</b> <span class="more">' +
          esc(t('board_upstream.more', {k: k})) + '</span></span></li>';
      }
      return '';
    }).join('') + '</ul>';
  }

  function optHtml(o, list) {
    var c = summary(o), open = o.id === s.sel, k = c.level === ND ? null : kOf(c.p_seat);
    var chg = o.transfers ? t('changes', {n: o.transfers}) : t('changes.0');
    var lbl = [o.depart + ' → ' + o.arrive, o.total_min + ' min', chg, t('level.' + c.level), k != null ? t('seats_k_of_10', {k: k}) : ''].filter(Boolean).join(', ');
    var meta = [];
    if (c.confidence) meta.push('<span class="conf">' + esc(t('confidence.' + c.confidence)) + '</span>');
    if (c.n != null) meta.push('<span>' + esc(t('confidence.n', {n: c.n})) + '</span>');
    if (c.range && c.range.length === 2) meta.push('<span>' + esc(t('range', {a: t('level.' + c.range[0]), b: t('level.' + c.range[1])})) + '</span>');
    meta.push('<span class="onmap">' + esc(t('on_map')) + '</span>');
    var why = c.level === ND ? '<p class="why">' + icon('nodata') + '<span>' + esc(t('limited.' + (c.reason === 'schedule_gap' || c.reason === 'low_n' ? c.reason : 'generic'))) + '</span></p>' : '';
    return '<li class="opt' + (open ? ' sel' : '') + '" data-id="' + esc(o.id) + '">' +
      '<button type="button" class="row" aria-expanded="' + open + '" aria-controls="d-' + esc(o.id) + '" aria-label="' + esc(lbl) + '">' +
      '<span class="dep">' + esc(o.depart) + '</span><span class="arr">' + esc(o.arrive) + '</span>' +
      '<span class="min">' + esc(o.total_min) + '</span><span class="chg">' + esc(o.transfers) + '</span>' +
      '<span class="avail">' + chip(c.level) + (k != null ? '<span class="k">' + esc(t('avail.k', {k: k})) + '</span>' : '') + '</span>' +
      '<svg class="ic chev" aria-hidden="true"><use href="#i-chev"/></svg></button>' +
      '<div class="detail" id="d-' + esc(o.id) + '"' + (open ? '' : ' hidden') + '>' +
      '<p class="line">' + crowdLine(o, c) + '</p>' +
      '<p class="meta">' + meta.join('') + '</p>' + why +
      '<ol class="legs">' + (o.legs || []).map(legHtml).join('') + '</ol>' +
      suggestions(o, list) + '</div></li>';
  }

  function quiet() {
    var q = s.res && s.res.quiet_hour;
    if (!q || !q.level) return '';
    return '<p class="quiet">' + icon('clock') + '<span>' + esc(t('quiet_hour', {t: q.time, level: ''})).replace(/[:\s]+$/, '') + ':</span>' +
      chip(q.level, true) + (q.total_min != null ? '<span class="more">' + esc(t('quiet_hour.more', {m: q.total_min})) + '</span>' : '') + '</p>';
  }

  function head() {
    return '<div class="chart-head" aria-hidden="true"><span>' + esc(t('col.dep')) + '</span><span>' + esc(t('col.arr')) +
      '</span><span>' + esc(t('col.min')) + '</span><span>' + esc(t('col.chg')) + '</span><span>' + esc(t('col.avail')) + '</span><span></span></div>';
  }

  function render() {
    var el = $('#results'), st = s.status;
    el.setAttribute('aria-busy', st === 'loading' ? 'true' : 'false');
    $('#pref').hidden = st !== 'ok';
    if (st === 'loading') {
      el.innerHTML = head() + '<div aria-hidden="true">' + [0, 1, 2].map(function () { return '<div class="skel"><i></i><i></i><i></i><i></i><i></i></div>'; }).join('') + '</div>';
      say(t('loading'));
    } else if (st === 'error') {
      var msg = s.err === 'stops' ? t('err.stops') : t('err.api');
      el.innerHTML = '<div class="state" role="alert"><h2>' + esc(msg) + '</h2><div class="acts"><button type="button" class="btn" data-act="retry">' + esc(t('err.retry')) + '</button></div></div>';
    } else if (st === 'empty') {
      el.innerHTML = '<div class="state"><h2>' + esc(t('no_route')) + '</h2><p>' + esc(t('no_route.why')) + '</p><div class="acts">' +
        '<button type="button" class="btn" data-act="later">' + esc(t('no_route.later')) + '</button>' +
        '<button type="button" class="btn" data-act="edit">' + esc(t('no_route.edit')) + '</button></div></div>';
      say(t('no_route'));
    } else if (st === 'ok') {
      var o = sorted();
      el.innerHTML = head() + '<ol class="opts" aria-label="' + esc(t('options.label')) + '">' + o.map(function (x) { return optHtml(x, o); }).join('') + '</ol>' + quiet();
      say(t('options.count', {n: o.length, pref: t('pref.' + s.pref)}));
    } else {
      el.innerHTML = '';
    }
  }

  function say(x) { $('#status').textContent = x; }

  function select(id) {
    s.sel = s.sel === id ? null : id;
    $$('.opt').forEach(function (li) {
      var on = li.getAttribute('data-id') === s.sel;
      li.classList.toggle('sel', on);
      $('.row', li).setAttribute('aria-expanded', on ? 'true' : 'false');
      $('.detail', li).hidden = !on;
    });
    if (s.sel) draw();
  }

  // Re-sort in place with a 200 ms move, keeping focus on the same card.
  function resort() {
    var list = $('.opts');
    if (!list) return render();
    var foc = document.activeElement, before = {};
    $$('.opt', list).forEach(function (li) { before[li.getAttribute('data-id')] = li.getBoundingClientRect().top; });
    sorted().forEach(function (o) { list.appendChild($('.opt[data-id="' + CSS.escape(String(o.id)) + '"]', list)); });
    if (foc && list.contains(foc)) foc.focus({preventScroll: true});
    say(t('options.count', {n: $$('.opt', list).length, pref: t('pref.' + s.pref)}));
    if (matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    $$('.opt', list).forEach(function (li) {
      var dy = before[li.getAttribute('data-id')] - li.getBoundingClientRect().top;
      if (!dy) return;
      li.style.transition = 'none';
      li.style.transform = 'translateY(' + dy + 'px)';
      li.style.zIndex = '1';
      li.getBoundingClientRect();
      li.style.transition = 'transform 200ms cubic-bezier(0.2, 0, 0, 1)';
      li.style.transform = '';
      li.addEventListener('transitionend', function () { li.style.transition = ''; li.style.zIndex = ''; }, {once: true});
    });
  }

  // ---------- map ----------
  function css(v) { return getComputedStyle(document.documentElement).getPropertyValue(v).trim(); }

  function legend() {
    $('#legend').innerHTML = '<b>' + esc(t('map.legend')) + '</b>' + RANK.concat([ND]).map(function (l) {
      return '<span><i class="lv-' + lv(l) + '"></i>' + esc(t('level.' + l)) + '</span>';
    }).join('') + '<span><i class="course"></i>' + esc(t('map.trip')) + '</span><span><i class="walkln"></i>' + esc(t('map.walk')) + '</span>';
    var big = $('#mapwrap').classList.contains('big');
    $('#map-size span').textContent = t(big ? 'map.collapse' : 'map.expand');
  }

  function initMap() {
    if (!window.maplibregl) return mapFail();
    try {
      map = new maplibregl.Map({container: 'map', style: 'https://tiles.openfreemap.org/styles/liberty',
        center: [77.22, 28.63], zoom: 10.5, attributionControl: {compact: true}, cooperativeGestures: matchMedia('(max-width: 1023px)').matches});
    } catch (e) { return mapFail(); }
    map.addControl(new maplibregl.NavigationControl({showCompass: false}), 'bottom-right');
    map.on('load', function () {
      var lvl = ['match', ['get', 'level'],
        RANK[0], css('--crowd-1'), RANK[1], css('--crowd-2'), RANK[2], css('--crowd-3'), RANK[3], css('--crowd-4'), '#8f8f87'];
      map.addSource('trip', {type: 'geojson', data: {type: 'FeatureCollection', features: []}});
      map.addLayer({id: 'trip-course', type: 'line', source: 'trip', filter: ['==', ['get', 'kind'], 'bus'],
        layout: {'line-join': 'round', 'line-cap': 'round'}, paint: {'line-color': css('--course'), 'line-width': 14}});
      map.addLayer({id: 'trip-walk', type: 'line', source: 'trip', filter: ['==', ['get', 'kind'], 'walk'],
        layout: {'line-cap': 'round'}, paint: {'line-color': css('--course'), 'line-width': 3.5, 'line-dasharray': [0.5, 2]}});
      map.addLayer({id: 'trip-casing', type: 'line', source: 'trip', filter: ['==', ['get', 'kind'], 'bus'],
        layout: {'line-join': 'round', 'line-cap': 'round'}, paint: {'line-color': css('--paper'), 'line-width': 10}});
      map.addLayer({id: 'trip-level', type: 'line', source: 'trip', filter: ['==', ['get', 'kind'], 'bus'],
        layout: {'line-join': 'round'}, paint: {'line-color': lvl, 'line-width': 6}});
      map.addLayer({id: 'trip-stops', type: 'circle', source: 'trip', filter: ['==', ['get', 'kind'], 'stop'],
        paint: {'circle-radius': 5, 'circle-color': css('--paper'), 'circle-stroke-color': css('--ink'), 'circle-stroke-width': 2}});
      mapReady = true;
      popup = new maplibregl.Popup({closeButton: false, closeOnClick: false, offset: 8});
      map.on('mousemove', 'trip-level', function (e) {
        var p = e.features[0].properties;
        map.getCanvas().style.cursor = 'default';
        popup.setLngLat(e.lngLat).setHTML(esc(t('strip.cell', {a: p.from, b: p.to, level: t('level.' + p.level), m: p.min}))).addTo(map);
      });
      map.on('mouseleave', 'trip-level', function () { popup.remove(); });
      draw();
    });
    map.on('click', function (e) { if (s.picking) pickAt(e.lngLat); });
  }

  function mapFail() {
    var m = $('#map-msg');
    m.textContent = t('map.unavailable');
    m.hidden = false;
  }

  function pt(x) { return x && x.lon != null && x.lat != null ? [+x.lon, +x.lat] : null; }

  function features(o) {
    var f = [], q = (s.res && s.res.query) || {}, legs = o.legs || [], i, j;
    function end(k, dir) {
      for (var n = k + dir; n >= 0 && n < legs.length; n += dir) {
        if (legs[n].mode !== 'bus') continue;
        var st = legs[n].stops;
        return st && st.length ? pt(dir < 0 ? st[st.length - 1] : st[0]) : null;
      }
      return pt(dir < 0 ? q.from_point || s.from : q.to_point || s.to);
    }
    for (i = 0; i < legs.length; i++) {
      var l = legs[i];
      if (l.mode === 'walk') {
        var a = end(i, -1), b = end(i, 1);
        if (a && b) f.push({type: 'Feature', properties: {kind: 'walk'}, geometry: {type: 'LineString', coordinates: [a, b]}});
        continue;
      }
      var st = (l.stops || []).map(pt).filter(Boolean), segs = l.segments || [];
      if (st.length < 2) continue;
      for (j = 0; j < st.length - 1; j++) {
        var g = segs[j] || {from: l.board, to: l.alight, min: l.ride_min, level: (l.crowding || {}).level || ND};
        f.push({type: 'Feature', properties: {kind: 'bus', level: g.level || ND, from: g.from, to: g.to, min: g.min},
          geometry: {type: 'LineString', coordinates: g.shape || [st[j], st[j + 1]]}});
      }
      f.push({type: 'Feature', properties: {kind: 'stop'}, geometry: {type: 'Point', coordinates: st[0]}});
      f.push({type: 'Feature', properties: {kind: 'stop'}, geometry: {type: 'Point', coordinates: st[st.length - 1]}});
    }
    return f;
  }

  function draw() {
    if (!mapReady) return;
    var o = s.status === 'ok' && sorted().filter(function (x) { return x.id === s.sel; })[0];
    var f = o ? features(o) : [];
    map.getSource('trip').setData({type: 'FeatureCollection', features: f});
    if (!f.length) return;
    var b = new maplibregl.LngLatBounds();
    f.forEach(function (x) { (x.geometry.type === 'Point' ? [x.geometry.coordinates] : x.geometry.coordinates).forEach(function (c) { b.extend(c); }); });
    map.fitBounds(b, {padding: {top: 90, bottom: 40, left: 40, right: 60}, maxZoom: 15, duration: matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 600});
  }

  function pickAt(ll) {
    var field = s.picking;
    s.picking = null;
    $$('.pick').forEach(function (b) { b.setAttribute('aria-pressed', 'false'); });
    map.getCanvas().style.cursor = '';
    var m = 0.02, bx = s.box;
    if (!bx || ll.lng < bx[0] - m || ll.lat < bx[1] - m || ll.lng > bx[2] + m || ll.lat > bx[3] + m) {
      $('#form-msg').textContent = t('err.outside');
      return;
    }
    var best = null, bd = Infinity, k = Math.cos(ll.lat * Math.PI / 180);
    s.stops.forEach(function (x) {
      var d = Math.pow((x.lon - ll.lng) * k, 2) + Math.pow(x.lat - ll.lat, 2);
      if (d < bd) { bd = d; best = x; }
    });
    if (best) { setField(field, best); say(t('pick.set', {field: t(field), stop: best.name})); $('#' + field).focus(); }
  }

  // ---------- language ----------
  function setLang(l) {
    lang = I18N[l] ? l : 'en';
    document.documentElement.lang = lang;
    store('seatcast.lang', lang);
    $$('[data-lang]').forEach(function (b) { b.setAttribute('aria-pressed', b.getAttribute('data-lang') === lang ? 'true' : 'false'); });
    $$('[data-i18n]').forEach(function (e) { e.textContent = t(e.getAttribute('data-i18n')); });
    $$('[data-i18n-ph]').forEach(function (e) { e.placeholder = t(e.getAttribute('data-i18n-ph')); });
    $$('[data-i18n-aria]').forEach(function (e) { e.setAttribute('aria-label', t(e.getAttribute('data-i18n-aria'))); });
    $$('[data-i18n-title]').forEach(function (e) { e.title = t(e.getAttribute('data-i18n-title')); });
    $$('.pick').forEach(function (b) { b.title = t('pick_on_map'); });
    enquiry();
    legend();
    if (s.status !== 'idle') render();
  }

  // ---------- tabs ----------
  function tab(btn, focus) {
    $$('[role="tab"]').forEach(function (b) {
      var on = b === btn;
      b.setAttribute('aria-selected', on ? 'true' : 'false');
      b.tabIndex = on ? 0 : -1;
      $('#' + b.getAttribute('aria-controls')).hidden = !on;
    });
    if (focus) btn.focus();
    if (map && btn.id === 'tab-planner') map.resize();
  }

  // ---------- wiring ----------
  function wire() {
    combo('from');
    combo('to');
    $('#daytype').value = s.daytype;
    $('#time').value = s.time;
    $('#form').addEventListener('submit', function (e) {
      e.preventDefault();
      s.daytype = $('#daytype').value;
      s.time = $('#time').value || DEFAULT.time;
      search();
    });
    $('#swap').addEventListener('click', function () { var a = s.from; setField('from', s.to); setField('to', a); });
    $('#edit').addEventListener('click', function () { showForm(true); $('#from').focus(); });
    $$('.pick').forEach(function (b) {
      b.setAttribute('aria-pressed', 'false');
      b.addEventListener('click', function () {
        var f = b.getAttribute('data-pick');
        if (!map) { mapFail(); return; }
        s.picking = s.picking === f ? null : f;
        $$('.pick').forEach(function (x) { x.setAttribute('aria-pressed', x.getAttribute('data-pick') === s.picking ? 'true' : 'false'); });
        if (!s.picking) return;
        map.getCanvas().style.cursor = 'crosshair';
        say(t('pick.hint', {field: t(f)}));
        $('#form-msg').textContent = '';
        if (matchMedia('(max-width: 1023px)').matches) $('#mapwrap').scrollIntoView({behavior: 'smooth', block: 'center'});
      });
    });
    $$('input[name="pref"]').forEach(function (r) {
      r.addEventListener('change', function () { s.pref = r.value; resort(); });
    });
    $('#results').addEventListener('click', function (e) {
      var row = e.target.closest('.row');
      if (row) return select(row.parentNode.getAttribute('data-id'));
      var b = e.target.closest('[data-act]');
      if (!b) return;
      var a = b.getAttribute('data-act');
      if (a === 'retry') { if (s.err === 'stops') { s.err = ''; boot(); } else search(); }
      if (a === 'later') { s.time = hhmm(mins(s.time) + 60); $('#time').value = s.time; search(); }
      if (a === 'edit') { showForm(true); $('#from').focus(); }
    });
    $$('[data-lang]').forEach(function (b) { b.addEventListener('click', function () { setLang(b.getAttribute('data-lang')); }); });
    var tabs = $$('[role="tab"]');
    tabs.forEach(function (b, i) {
      b.addEventListener('click', function () { tab(b); });
      b.addEventListener('keydown', function (e) {
        var j = {ArrowRight: i + 1, ArrowLeft: i - 1, Home: 0, End: tabs.length - 1}[e.key];
        if (j == null) return;
        e.preventDefault();
        tab(tabs[(j + tabs.length) % tabs.length], true);
      });
    });
    $('#map-size').addEventListener('click', function () {
      var w = $('#mapwrap'), big = w.classList.toggle('big');
      this.setAttribute('aria-expanded', big ? 'true' : 'false');
      legend();
      if (map) requestAnimationFrame(function () { map.resize(); draw(); });
    });
  }

  function start() {
    if (Data.fixture) $('#fixture').hidden = false;
    wire();
    setLang(store('seatcast.lang') || 'en');
    initMap();
    boot();
  }

  start();
})();
