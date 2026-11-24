(function () {
  'use strict';

  var RANK = ['MANY_SEATS_AVAILABLE', 'FEW_SEATS_AVAILABLE', 'STANDING_ROOM_ONLY', 'CRUSHED_STANDING_ROOM_ONLY'];
  var ICON = {MANY_SEATS_AVAILABLE: 'seat2', FEW_SEATS_AVAILABLE: 'seat1', STANDING_ROOM_ONLY: 'stand', CRUSHED_STANDING_ROOM_ONLY: 'crowd', NO_DATA_AVAILABLE: 'nodata'};
  var ND = 'NO_DATA_AVAILABLE';
  // the brief's example (§2.2). The main-road Anand Vihar stop, not the ISBT terminus, where everyone gets a seat
  var DEFAULT = {from: 'anand vihar', fromId: '5694', to: 'connaught place', toId: '365', daytype: 'weekday', time: '18:00'};
  var FORM_ERR = {same_stop: ['to', 'err.same'], outside_area: ['from', 'err.outside'], unknown_stop: ['from', 'err.unknown_stop'],
                  bad_depart: ['time', 'err.input'], invalid_input: ['time', 'err.input']};

  var s = {stops: [], box: null, from: null, to: null, daytype: DEFAULT.daytype, time: DEFAULT.time,
           pref: 'fastest', res: null, sel: null, status: 'idle', err: '', picking: null, seq: 0, tab: 'planner'};
  var op = {day: 'weekday', hour: 18, period: 'all', rows: null, err: false, sort: {k: 'gap_obs', d: -1},
            sel: null, prof: null, heat: null, hseq: 0, pseq: 0, tseq: 0, keys: [], started: false};
  var cov = {res: null, err: false, started: false};
  var map = null, mapReady = false, popup = null;
  var nf = new Intl.NumberFormat('en-IN');

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
  function hr(h) { return hhmm(h * 60); }
  function num(x, d) { return x == null || isNaN(x) ? '–' : nf.format(d ? +(+x).toFixed(d) : Math.round(x)); }
  function store(k, v) { try { if (v === undefined) return localStorage.getItem(k); localStorage.setItem(k, v); } catch (e) { return null; } }
  function reduced() { return matchMedia('(prefers-reduced-motion: reduce)').matches; }

  // Very crowded with low confidence: the model caps loads far above capacity, so the number is uncertain.
  function unsure(c) { return !!c && c.level === RANK[3] && c.confidence === 'low'; }

  function chip(level, small, later) {
    level = level || ND;
    var word = later && rank(level) >= 2 ? t('later.' + level) : t('short.' + level);
    return '<span class="chip lv-' + lv(level) + (small ? ' sm' : '') + '">' + icon(ICON[level] || 'nodata') +
      '<span>' + esc(word) + '</span></span>';
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

  function byId(id) {
    return s.stops.filter(function (x) { return String(x.stop_id) === id; })[0];
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

  function formErr(field, msg) {
    s.status = 'idle';
    render();
    showForm(true);
    $('#form-msg').textContent = msg;
    $('#' + field).setAttribute('aria-invalid', 'true');
    $('#' + field).focus();
  }

  function search() {
    var bad = check();
    if (bad) return formErr(bad[0], bad[1]);
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
      }, function (e) {
        if (n !== s.seq) return;
        var f = FORM_ERR[e && e.code];
        if (f) { draw(); return formErr(f[0], t(f[1])); }
        s.status = 'error';
        s.err = e && e.code === 'network' ? 'api' : 'server';
        render();
        draw();
      });
  }

  function boot() {
    s.status = 'loading';
    render();
    Data.stops().then(function (list) {
      setStops(list);
      setField('from', byId(DEFAULT.fromId) || find(DEFAULT.from, 1)[0] || null);
      setField('to', byId(DEFAULT.toId) || find(DEFAULT.to, 1)[0] || null);
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

  // A leg is "crowded later" when its worst level is standing or worse but the stretch you board on is not:
  // the seat chance at boarding (p_seat) can then be high next to a STANDING chip without contradiction.
  function laterLeg(l) {
    var c = l.crowding || {};
    if (rank(c.level) < 2) return false;
    var g = (l.segments || []).filter(function (x) { return x.level && x.level !== ND; })[0];
    return !!g && rank(g.level) < 2;
  }

  // Option-level summary: the API's option crowding when present, else worst leg level and lowest seat chance.
  function summary(o) {
    var b = buses(o);
    if (!b.length) return {walk: true};
    var c = o.crowding;
    if (!c) {
      var cs = b.map(function (l) { return l.crowding || {level: ND}; });
      var nd = cs.some(function (x) { return !x.level || x.level === ND; });
      var ps = cs.map(function (x) { return x.p_seat; }).filter(function (p) { return p != null; });
      var ns = cs.map(function (x) { return x.n; }).filter(function (n) { return n != null; });
      c = {level: nd ? ND : cs.reduce(function (a, x) { return rank(x.level) > rank(a.level) ? x : a; }).level,
           p_seat: nd || !ps.length ? null : Math.min.apply(0, ps),
           confidence: ['low', 'medium', 'high'].filter(function (k) { return cs.some(function (x) { return x.confidence === k; }); })[0],
           n: ns.length ? Math.min.apply(0, ns) : null,
           reason: (cs.filter(function (x) { return x.reason; })[0] || {}).reason};
    }
    if (!c.reason && c.level === ND) c.reason = (b.map(function (l) { return (l.crowding || {}).reason; }).filter(Boolean))[0];
    var crowdedLegs = b.filter(function (l) { return rank((l.crowding || {}).level) >= 2; });
    c.later = rank(c.level) >= 2 && crowdedLegs.length > 0 && crowdedLegs.every(laterLeg);
    return c;
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
    var out = r.map(function (x, i) {
      var a = segs[x.a].from, b = segs[x.b].to;
      // claim "seats until a" only when every stretch before the crowding has data
      return i === 0 && x.a > 0 && !nd ? t('strip.until', {a: a, b: b}) : t('strip.from', {a: a, b: b});
    }).join('; ');
    return nd ? out + '; ' + t('strip.some_nd') : out;
  }

  function strip(leg) {
    var segs = leg.segments && leg.segments.length ? leg.segments
      : [{from: leg.board, to: leg.alight, min: leg.ride_min || 1, level: (leg.crowding || {}).level || ND}];
    var cols = segs.map(function (g) { return 'minmax(6px, ' + Math.max(+g.min || 1, 1) + 'fr)'; }).join(' ');
    var cells = segs.map(function (g, i) {
      var tip = t('strip.cell', {a: g.from, b: g.to, level: t('level.' + (g.level || ND)), m: num(g.min, 1)});
      return '<span class="cell lv-' + lv(g.level) + '" style="grid-column:' + (i + 1) + '" title="' + esc(tip) + '"></span>';
    }).join('');
    var marks = runs(segs).map(function (x) { return '<span class="run" style="grid-column:' + (x.a + 1) + ' / ' + (x.b + 2) + '"></span>'; }).join('');
    var txt = stripText(segs);
    return '<div class="strip-wrap"><div class="strip" role="img" aria-label="' + esc(t('strip.label', {s: txt})) +
      '" style="grid-template-columns:' + cols + '">' + cells + marks + '</div></div>' +
      '<p class="strip-text" aria-hidden="true">' + esc(txt) + '</p>';
  }

  function crowdLine(o, c) {
    var parts = [], k = kOf(c.p_seat);
    if (c.level === ND) parts.push(esc(t('level.' + ND)));
    else if (k != null) parts.push(esc(t(c.later ? 'seat_later' : 'seats_k_of_10', {k: k})));
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
      chip(c.level, true, laterLeg(l)) + (k != null ? '<span class="k">' + esc(t('avail.k', {k: k})) + '</span>' : '') +
      (unsure(c) ? '<span class="unc">' + esc(t('censored.short')) + '</span>' : '') +
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

  function why(c) {
    var r = {low_n: 1, schedule_gap: 1, implausible: 1}[c.reason] ? c.reason : 'generic';
    return '<p class="why">' + icon('nodata') + '<span>' + esc(t('limited.' + r)) + '</span></p>';
  }

  function optHtml(o, list) {
    var c = summary(o), open = o.id === s.sel, k = c.walk || c.level === ND ? null : kOf(c.p_seat);
    var chg = o.transfers ? t('changes', {n: o.transfers}) : t('changes.0');
    var word = c.walk ? t('walk.only') : c.later && rank(c.level) >= 2 ? t('later.' + c.level) : t('level.' + c.level);
    var lbl = [o.depart + ' → ' + o.arrive, o.total_min + ' min', chg, word,
               k != null ? t(c.later ? 'seat_later' : 'seats_k_of_10', {k: k}) : '', unsure(c) ? t('censored.short') : ''].filter(Boolean).join(', ');
    var avail = c.walk ? '<span class="chip walkchip">' + icon('walk') + '<span>' + esc(t('walk.only')) + '</span></span>'
      : chip(c.level, false, c.later) + (k != null ? '<span class="k">' + esc(t('avail.k', {k: k})) + '</span>' : '');  // one-second read: chip + k only; uncertainty sits in the detail
    var body;
    if (c.walk) {
      body = '<p class="line">' + esc(t('walk.only.line', {m: o.total_min})) + '</p>';
    } else {
      var meta = [];
      if (c.confidence) meta.push('<span class="conf">' + esc(t('confidence.' + c.confidence)) + '</span>');
      if (c.n != null) meta.push('<span>' + esc(t('confidence.n', {n: num(c.n)})) + '</span>');
      if (c.range && c.range.length === 2 && !(c.range[0] === c.range[1] && c.range[0] === c.level)) meta.push('<span>' + esc(c.range[0] === c.range[1] ? t('range.one', {a: t('level.' + c.range[0])}) : t('range', {a: t('level.' + c.range[0]), b: t('level.' + c.range[1])})) + '</span>');
      meta.push('<span class="onmap">' + esc(t('on_map')) + '</span>');
      body = '<p class="line">' + crowdLine(o, c) + '</p><p class="meta">' + meta.join('') + '</p>' + (c.level === ND ? why(c) : '') +
        (unsure(c) ? '<p class="why">' + icon('crowd') + '<span>' + esc(t('censored.long')) + '</span></p>' : '');
    }
    return '<li class="opt' + (open ? ' sel' : '') + '" data-id="' + esc(o.id) + '">' +
      '<button type="button" class="row" aria-expanded="' + open + '" aria-controls="d-' + esc(o.id) + '" aria-label="' + esc(lbl) + '">' +
      '<span class="dep">' + esc(o.depart) + '</span><span class="arr">' + esc(o.arrive) + '</span>' +
      '<span class="min">' + esc(o.total_min) + '</span><span class="chg">' + esc(o.transfers) + '</span>' +
      '<span class="avail">' + avail + '</span>' +
      '<svg class="ic chev" aria-hidden="true"><use href="#i-chev"/></svg></button>' +
      '<div class="detail" id="d-' + esc(o.id) + '"' + (open ? '' : ' hidden') + '>' + body +
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
      var msg = {stops: 'err.stops', server: 'err.server'}[s.err] || 'err.api';
      el.innerHTML = '<div class="state" role="alert"><h2>' + esc(t(msg)) + '</h2><div class="acts"><button type="button" class="btn" data-act="retry">' + esc(t('err.retry')) + '</button></div></div>';
    } else if (st === 'empty') {
      var key = s.res && s.res.reason === 'no_stop_nearby' ? 'no_stop_nearby' : 'no_route';
      el.innerHTML = '<div class="state"><h2>' + esc(t(key)) + '</h2><p>' + esc(t(key + '.why')) + '</p><div class="acts">' +
        (key === 'no_route' ? '<button type="button" class="btn" data-act="later">' + esc(t('no_route.later')) + '</button>' : '') +
        '<button type="button" class="btn" data-act="edit">' + esc(t('no_route.edit')) + '</button></div></div>';
      say(t(key));
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
    if (reduced()) return;
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

  // ---------- map (one map, moved between the planner and operator tabs) ----------
  function css(v) { return getComputedStyle(document.documentElement).getPropertyValue(v).trim(); }

  function legend() {
    var lv5 = RANK.concat([ND]).map(function (l) { return '<span><i class="lv-' + lv(l) + '"></i>' + esc(t('level.' + l)) + '</span>'; }).join('');
    $('#legend').innerHTML = '<b>' + esc(t('map.legend')) + '</b>' + lv5 + (s.tab === 'operator'
      ? '<span><i class="widths"></i>' + esc(t('op.legend_width')) + '</span><span><i class="course"></i>' + esc(t('op.legend_sel')) + '</span>'
      : '<span><i class="course"></i>' + esc(t('map.trip')) + '</span><span><i class="walkln"></i>' + esc(t('map.walk')) + '</span>');
    var big = $('#mapwrap').classList.contains('big');
    $('#map-size span').textContent = t(big ? 'map.collapse' : 'map.expand');
    $('#map').setAttribute('aria-label', t(s.tab === 'operator' ? 'op.map_label' : 'map.label'));
  }

  function lvColor() {
    return ['match', ['get', 'level'], RANK[0], css('--crowd-1'), RANK[1], css('--crowd-2'), RANK[2], css('--crowd-3'), RANK[3], css('--crowd-4'), '#8f8f87'];
  }

  function initMap() {
    if (!window.maplibregl) return mapFail();
    try {
      map = new maplibregl.Map({container: 'map', style: 'https://tiles.openfreemap.org/styles/liberty',
        center: [77.22, 28.63], zoom: 10.5, attributionControl: {compact: true}, cooperativeGestures: matchMedia('(max-width: 1023px)').matches});
    } catch (e) { return mapFail(); }
    map.addControl(new maplibregl.NavigationControl({showCompass: false}), 'bottom-right');
    map.on('load', function () {
      var empty = {type: 'FeatureCollection', features: []};
      var w = function (k) { return ['match', ['get', 'level'], RANK[0], 0.7 * k, RANK[1], 1.1 * k, RANK[2], 1.8 * k, RANK[3], 2.6 * k, 0.7 * k]; };
      map.addSource('heat', {type: 'geojson', data: empty});
      map.addLayer({id: 'heat-sel', type: 'line', source: 'heat', filter: ['in', ['get', 'key'], ['literal', []]],
        layout: {'line-join': 'round', 'line-cap': 'round', visibility: 'none'}, paint: {'line-color': css('--course'), 'line-width': ['interpolate', ['linear'], ['zoom'], 10, 7, 15, 16]}});
      map.addLayer({id: 'heat', type: 'line', source: 'heat',
        layout: {'line-join': 'round', 'line-cap': 'round', 'line-sort-key': ['match', ['get', 'level'], RANK[0], 0, RANK[1], 1, RANK[2], 2, RANK[3], 3, -1], visibility: 'none'},
        paint: {'line-color': lvColor(), 'line-width': ['interpolate', ['linear'], ['zoom'], 10, w(1), 15, w(3)]}});
      map.addSource('trip', {type: 'geojson', data: empty});
      map.addLayer({id: 'trip-course', type: 'line', source: 'trip', filter: ['==', ['get', 'kind'], 'bus'],
        layout: {'line-join': 'round', 'line-cap': 'round'}, paint: {'line-color': css('--course'), 'line-width': 14}});
      map.addLayer({id: 'trip-walk', type: 'line', source: 'trip', filter: ['==', ['get', 'kind'], 'walk'],
        layout: {'line-cap': 'round'}, paint: {'line-color': css('--course'), 'line-width': 3.5, 'line-dasharray': [0.5, 2]}});
      map.addLayer({id: 'trip-casing', type: 'line', source: 'trip', filter: ['==', ['get', 'kind'], 'bus'],
        layout: {'line-join': 'round', 'line-cap': 'round'}, paint: {'line-color': css('--paper'), 'line-width': 10}});
      map.addLayer({id: 'trip-level', type: 'line', source: 'trip', filter: ['==', ['get', 'kind'], 'bus'],
        layout: {'line-join': 'round'}, paint: {'line-color': lvColor(), 'line-width': 6}});
      map.addLayer({id: 'trip-stops', type: 'circle', source: 'trip', filter: ['==', ['get', 'kind'], 'stop'],
        paint: {'circle-radius': 5, 'circle-color': css('--paper'), 'circle-stroke-color': css('--ink'), 'circle-stroke-width': 2}});
      mapReady = true;
      popup = new maplibregl.Popup({closeButton: false, closeOnClick: false, offset: 8});
      map.on('mousemove', 'trip-level', function (e) {
        var p = e.features[0].properties;
        popup.setLngLat(e.lngLat).setHTML(esc(t('strip.cell', {a: p.from, b: p.to, level: t('level.' + p.level), m: num(p.min, 1)}))).addTo(map);
      });
      map.on('mouseleave', 'trip-level', function () { popup.remove(); });
      var heatTip = function (e) {
        var p = e.features[0].properties;
        map.getCanvas().style.cursor = 'pointer';
        popup.setLngLat(e.lngLat).setHTML(esc(t('op.tip', {a: p.from, b: p.to, level: t('level.' + p.level), lf: num(p.LF, 1), r: p.routes}))).addTo(map);
      };
      map.on('mousemove', 'heat', heatTip);
      map.on('click', 'heat', heatTip);
      map.on('mouseleave', 'heat', function () { map.getCanvas().style.cursor = ''; popup.remove(); });
      mode();
      draw();
      if (op.heat) heatData();
    });
    map.on('click', function (e) { if (s.picking) pickAt(e.lngLat); });
  }

  // Show the layers that belong to the open tab.
  function mode() {
    if (!mapReady) return;
    var opm = s.tab === 'operator';
    ['heat', 'heat-sel'].forEach(function (id) { map.setLayoutProperty(id, 'visibility', opm ? 'visible' : 'none'); });
    ['trip-course', 'trip-walk', 'trip-casing', 'trip-level', 'trip-stops'].forEach(function (id) { map.setLayoutProperty(id, 'visibility', opm ? 'none' : 'visible'); });
    if (popup) popup.remove();
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
          geometry: {type: 'LineString', coordinates: g.shape && g.shape.length > 1 ? g.shape : [st[j], st[j + 1]]}});
      }
      f.push({type: 'Feature', properties: {kind: 'stop'}, geometry: {type: 'Point', coordinates: st[0]}});
      f.push({type: 'Feature', properties: {kind: 'stop'}, geometry: {type: 'Point', coordinates: st[st.length - 1]}});
    }
    return f;
  }

  function fit(f) {
    if (!f.length) return;
    var b = new maplibregl.LngLatBounds();
    f.forEach(function (x) { (x.geometry.type === 'Point' ? [x.geometry.coordinates] : x.geometry.coordinates).forEach(function (c) { b.extend(c); }); });
    map.fitBounds(b, {padding: {top: 90, bottom: 40, left: 40, right: 60}, maxZoom: 15, duration: reduced() ? 0 : 600});
  }

  function draw() {
    if (!mapReady) return;
    var o = s.status === 'ok' && sorted().filter(function (x) { return x.id === s.sel; })[0];
    var f = o ? features(o) : [];
    map.getSource('trip').setData({type: 'FeatureCollection', features: f});
    if (s.tab === 'planner') fit(f);
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

  // ---------- operator tab ----------
  function heatData() {
    if (!mapReady || !op.heat) return;
    op.heat.features.forEach(function (f) { f.properties.key = f.properties.from + '|' + f.properties.to; });
    map.getSource('heat').setData(op.heat);
    heatSel();
  }

  function heatSel() {
    if (!mapReady) return;
    map.setFilter('heat-sel', ['in', ['get', 'key'], ['literal', op.keys]]);
    if (!op.keys.length || !op.heat || s.tab !== 'operator') return;
    var set = {};
    op.keys.forEach(function (k) { set[k] = 1; });
    fit(op.heat.features.filter(function (f) { return set[f.properties.key]; }));
  }

  function loadHeat() {
    var n = ++op.hseq, h = hr(op.hour) + '–' + hr(op.hour + 1);
    $('#op-map-status').textContent = t('op.map_loading', {h: h});
    Data.heatmap(op.day, op.hour).then(function (gj) {
      if (n !== op.hseq) return;
      op.heat = gj;
      heatData();
      $('#op-map-status').textContent = t('op.map_status', {n: num((gj.features || []).length), day: t('daytype.' + op.day), h: h});
    }, function () {
      if (n === op.hseq) $('#op-map-status').textContent = t('op.map_err');
    });
  }

  var COLS = [
    {k: 'route', l: 'op.c.route'},
    {k: 'plus1_benefit', l: 'op.c.plus1', n: 1}, {k: 'standee_min', l: 'op.c.standee', n: 1}, {k: 'F_req', l: 'op.c.buses', n: 1},
    {k: 'gap_obs', l: 'op.c.gap', n: 1}, {k: 'LF_max', l: 'op.c.lf', n: 1}, {k: 'P_max', l: 'op.c.pax', n: 1}];

  function rowKey(r) { return r.route + '@' + r.hour; }
  function routeLabel(r) { return r.base + ' ' + r.dir; }
  function buses1(x) { return x == null ? '–' : Math.abs(x - Math.round(x)) < 0.05 ? num(x) : num(x, 1); }

  function loadTop() {
    var n = ++op.tseq;
    op.rows = null;
    op.err = false;
    renderTable();
    Data.top(op.day, op.period).then(function (rows) {
      if (n !== op.tseq) return;
      op.rows = rows.slice(0, 20);
      renderTable();
    }, function () {
      if (n !== op.tseq) return;
      op.err = true;
      renderTable();
    });
  }

  function renderTable() {
    var el = $('#op-table');
    if (op.err) {
      el.innerHTML = '<div class="state" role="alert"><h2>' + esc(t('op.err')) + '</h2><div class="acts"><button type="button" class="btn" data-op="retry">' + esc(t('err.retry')) + '</button></div></div>';
      return;
    }
    if (!op.rows) { el.innerHTML = '<p class="hint">' + esc(t('op.loading')) + '</p>'; return; }
    if (!op.rows.length) { el.innerHTML = '<p class="hint">' + esc(t('op.empty')) + '</p>'; return; }
    var k = op.sort.k, d = op.sort.d;
    var rows = op.rows.slice().sort(function (a, b) {
      var x = a[k], y = b[k];
      return (typeof x === 'string' ? String(x).localeCompare(y) : (x == null ? -1e12 : x) - (y == null ? -1e12 : y)) * d;
    });
    var th = COLS.map(function (c) {
      var on = c.k === k, sort = on ? (d > 0 ? 'ascending' : 'descending') : 'none';
      return '<th scope="col" aria-sort="' + sort + '"' + (c.n ? ' class="n"' : '') + '><button type="button" data-sort="' + c.k + '">' +
        esc(t(c.l)) + '<span class="dir" aria-hidden="true">' + (on ? (d > 0 ? '▲' : '▼') : '') + '</span></button></th>';
    }).join('');
    var tr = rows.map(function (r) {
      var on = rowKey(r) === op.sel;
      return '<tr' + (on ? ' class="sel"' : '') + '>' +
        '<th scope="row"><button type="button" class="rt" data-row="' + esc(rowKey(r)) + '" aria-pressed="' + on + '" lang="en">' + esc(routeLabel(r)) + '</button>' +
        '<span class="hh tnum">' + hr(r.hour) + '–' + hr(r.hour + 1) + '</span>' +
        '<span class="st"><span class="sr-only">' + esc(t('op.c.stretch')) + ': </span><span lang="en">' + esc(r.max_from) + ' → ' + esc(r.max_to) + '</span></span></th>' +
        '<td class="n b">' + num(r.plus1_benefit) + '</td>' +
        '<td class="n">' + num(r.standee_min) + '</td>' +
        '<td class="n">' + buses1(r.F_obs) + ' → ' + buses1(r.F_req) + '</td>' +
        '<td class="n">+' + buses1(r.gap_obs) + '</td>' +
        '<td class="n">' + num(r.LF_max, 1) + '×' + (r.censored ? ' <span class="unc">' + esc(t('censored.short')) + '</span>' : '') + '</td>' +
        '<td class="n">' + num(r.P_max) + '</td></tr>';
    }).join('');
    el.innerHTML = '<div class="tablewrap" tabindex="0" role="region" aria-label="' + esc(t('op.top')) + '"><table class="optable"><thead><tr>' + th +
      '</tr></thead><tbody>' + tr + '</tbody></table></div>';
  }

  function pickRow(key) {
    var r = (op.rows || []).filter(function (x) { return rowKey(x) === key; })[0];
    if (!r) return;
    op.sel = key;
    renderTable();
    if (op.hour !== r.hour) { op.hour = r.hour; $('#op-hour').value = r.hour; hourOut(); loadHeat(); }
    loadProfile(r);
  }

  function loadProfile(r) {
    var n = ++op.pseq, el = $('#op-profile');
    op.prof = {row: r, res: null, err: false};
    el.innerHTML = '<p class="hint">' + esc(t('op.loading')) + '</p>';
    Data.route(r.base, r.dir, op.day, hr(r.hour)).then(function (res) {
      if (n !== op.pseq) return;
      op.prof.res = res;
      op.keys = (res.segments || []).map(function (g) { return g.from + '|' + g.to; });
      renderProfile();
      el.scrollIntoView({block: 'nearest', behavior: reduced() ? 'auto' : 'smooth'});
      heatSel();
    }, function () {
      if (n !== op.pseq) return;
      op.prof.err = true;
      op.keys = [];
      renderProfile();
      heatSel();
    });
  }

  // Seats per bus are not in the route response; recover them from L / LF on well-loaded stretches.
  function seatsOf(segs) {
    var v = segs.filter(function (g) { return g.L > 0 && g.LF >= 0.3; }).map(function (g) { return g.L / g.LF; }).sort(function (a, b) { return a - b; });
    return v.length ? Math.round(v[Math.floor(v.length / 2)]) : null;
  }

  function renderProfile() {
    var el = $('#op-profile'), p = op.prof;
    if (!p) { el.innerHTML = ''; return; }
    var r = p.row;
    var title = '<h2 class="title2" lang="' + lang + '">' + esc(t('op.p.title', {route: routeLabel(r), day: t('daytype.' + op.day), h: hr(r.hour)})) + '</h2>';
    if (p.err) { el.innerHTML = title + '<p class="hint" role="alert">' + esc(t('op.p.err')) + '</p>'; return; }
    if (!p.res) return;
    var segs = (p.res.segments || []).filter(function (g) { return g.L != null; });
    if (!segs.length) { el.innerHTML = title + '<p class="hint">' + esc(t('op.p.empty')) + '</p>'; return; }
    var seats = seatsOf(segs);
    var top = segs.reduce(function (a, g) { return g.L > a.L ? g : a; });
    var peak = t('op.p.peak', {l: num(top.L), a: top.from, b: top.to});
    var W = Math.max(el.clientWidth || 600, 300), H = 230, ml = 40, mr = 10, mt = 16, mb = 40;
    var ymax = Math.max.apply(0, segs.map(function (g) { return g.L_high != null ? g.L_high : g.L; }).concat([seats ? seats * 1.15 : 0, 1]));
    var step = Math.pow(10, Math.floor(Math.log10(ymax / 2))), nice = Math.ceil(ymax / step) * step;
    var y = function (v) { return mt + (H - mt - mb) * (1 - v / nice); };
    var bw = (W - ml - mr) / segs.length, gap = bw > 6 ? 2 : 1;
    var ticks = [0, nice / 2, nice].map(function (v) {
      return '<line class="grid" x1="' + ml + '" x2="' + (W - mr) + '" y1="' + y(v) + '" y2="' + y(v) + '"/>' +
        '<text class="ax" x="' + (ml - 6) + '" y="' + (y(v) + 4) + '" text-anchor="end">' + num(v) + '</text>';
    }).join('');
    var bars = segs.map(function (g, i) {
      var x = ml + i * bw, cx = x + bw / 2, hgt = Math.max(y(0) - y(g.L), 1);
      var tip = t('op.p.bar', {a: g.from, b: g.to, l: num(g.L), lo: num(g.L_low), hi: num(g.L_high), level: t('level.' + g.level), n: num(g.n)}) +
        (unsure(g) ? ' ∙ ' + t('censored.short') : '');
      var lo = g.L_low != null ? y(g.L_low) : null, hi = g.L_high != null ? y(g.L_high) : null;
      return '<g class="bar"><title>' + esc(tip) + '</title>' +
        '<rect class="hit" x="' + x + '" y="' + mt + '" width="' + bw + '" height="' + (H - mt - mb) + '"/>' +
        '<rect class="lv-' + lv(g.level) + '" x="' + (x + gap / 2) + '" y="' + (y(0) - hgt) + '" width="' + Math.max(bw - gap, 1) + '" height="' + hgt + '" rx="' + (bw > 8 ? 2 : 0) + '"/>' +
        (unsure(g) ? '<rect class="unsure" x="' + (x + gap / 2) + '" y="' + (y(0) - hgt) + '" width="' + Math.max(bw - gap, 1) + '" height="' + hgt + '"/>' : '') +
        (lo != null && hi != null && hi < lo - 1 ? '<line class="wh" x1="' + cx + '" x2="' + cx + '" y1="' + hi + '" y2="' + lo + '"/>' : '') + '</g>';
    }).join('');
    var seatLine = seats ? '<line class="seats" x1="' + ml + '" x2="' + (W - mr) + '" y1="' + y(seats) + '" y2="' + y(seats) + '"/>' +
      '<text class="lab" x="' + (W - mr) + '" y="' + (y(seats) - 5) + '" text-anchor="end">' + esc(t('op.p.seats', {n: seats})) + '</text>' : '';
    var first = segs[0].from, last = segs[segs.length - 1].to;
    var xl = '<text class="ax" x="' + ml + '" y="' + (H - mb + 16) + '" lang="en">' + esc(first) + '</text>' +
      '<text class="ax" x="' + (W - mr) + '" y="' + (H - mb + 32) + '" text-anchor="end" lang="en">' + esc(last) + '</text>';
    var svg = '<svg class="pchart" width="' + W + '" height="' + H + '" viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="' +
      esc(t('op.p.chart', {s: peak + (seats ? '; ' + t('op.p.seats', {n: seats}) : '')})) + '">' +
      '<defs><pattern id="unsure" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="6" stroke="' + css('--paper') + '" stroke-width="2"/></pattern><pattern id="hatch" width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="5" height="5" fill="' + css('--crowd-0') + '"/><line x1="0" y1="0" x2="0" y2="5" stroke="' + css('--hatch') + '" stroke-width="2"/></pattern></defs>' +
      ticks + bars + seatLine + '<line class="base" x1="' + ml + '" x2="' + (W - mr) + '" y1="' + y(0) + '" y2="' + y(0) + '"/>' + xl + '</svg>';
    var rows = segs.map(function (g) {
      return '<tr><td lang="en">' + esc(g.from) + ' → ' + esc(g.to) + '</td><td class="n">' + num(g.L) + '</td><td class="n">' + num(g.L_low) + '–' + num(g.L_high) +
        '</td><td>' + esc(t('level.' + g.level)) + (unsure(g) ? ' ∙ ' + esc(t('censored.short')) : '') + '</td><td class="n">' + num(g.n) + '</td></tr>';
    }).join('');
    var nUnsure = segs.filter(unsure).length;
    el.innerHTML = title + '<p class="hint">' + esc(t('op.p.desc')) + (nUnsure ? ' ' + esc(t('op.p.censored')) : '') + '</p><p class="peak">' + esc(peak) + '</p>' +
      '<div class="pwrap">' + svg + '</div>' +
      '<details class="ptable"><summary>' + esc(t('op.p.table')) + '</summary><div class="tablewrap"><table class="optable"><thead><tr><th scope="col">' +
      esc(t('op.p.c.stretch')) + '</th><th scope="col" class="n">' + esc(t('op.p.c.load')) + '</th><th scope="col" class="n">' + esc(t('op.p.c.range')) +
      '</th><th scope="col">' + esc(t('op.p.c.level')) + '</th><th scope="col" class="n">' + esc(t('op.p.c.n')) + '</th></tr></thead><tbody>' + rows + '</tbody></table></div></details>';
  }

  function hourOut() {
    var h = hr(op.hour) + '–' + hr(op.hour + 1);
    $('#op-hour-out').textContent = h;
    $('#op-hour').setAttribute('aria-valuetext', h);
  }

  function opStart() {
    if (op.started) return;
    op.started = true;
    hourOut();
    loadHeat();
    loadTop();
  }

  // ---------- data tab ----------
  function pct(x, d) { return num(x, d == null ? 1 : d); }

  function renderData() {
    var el = $('#data-body');
    if (cov.err) {
      el.innerHTML = '<div class="state" role="alert"><h2>' + esc(t('data.err')) + '</h2><div class="acts"><button type="button" class="btn" data-cov="retry">' + esc(t('err.retry')) + '</button></div></div>';
      return;
    }
    var c = cov.res;
    if (!c) { el.innerHTML = '<p class="hint">' + esc(t('op.loading')) + '</p>'; return; }
    var m = c.match || {}, L = c.load || {}, g = c.gps || {}, E = L.E || {}, R = L.ridership_daily || {};
    var days = Object.keys(L.n_days || {}).reduce(function (a, k) { return a + L.n_days[k]; }, 0);
    var b = g.boarding || {}, bd = b.board || {}, al = b.alight || {}, dw = ((g.delivery_all_days || {}).weekday) || {};
    var rpb = deep(g, 'riders_per_bus_per_day_central');
    var share = L.level_share_pct || {}, conf = L.confidence_share_pct || {}, fl = L.cells_by_flag || {}, pk = L.weekday_flow_by_hour_peak || {};
    function sec(h, body) { return '<section class="dsec"><h2 class="title2">' + esc(t(h)) + '</h2>' + body + '</section>'; }
    function p(x) { return '<p>' + esc(x) + '</p>'; }
    function fig(label, v) { return '<div><dt>' + esc(t(label)) + '</dt><dd class="tnum">' + v + '</dd></div>'; }
    var bar = '<div class="stack" role="img" aria-label="' + esc(t('data.levels') + ': ' + RANK.map(function (l) { return t('level.' + l) + ' ' + pct(share[l]) + '%'; }).join(', ')) + '">' +
      RANK.map(function (l) { return '<span class="lv-' + lv(l) + '" style="flex-grow:' + (+share[l] || 0) + '"></span>'; }).join('') + '</div>' +
      '<ul class="stack-key" aria-hidden="true">' + RANK.map(function (l) {
        return '<li><i class="lv-' + lv(l) + '"></i>' + esc(t('level.' + l)) + ' <b class="tnum">' + pct(share[l]) + '%</b></li>';
      }).join('') + '</ul>';
    el.innerHTML =
      sec('data.method_h', '<ol class="method"><li>' + esc(t('data.m1')) + '</li><li>' + esc(t('data.m2')) + '</li><li>' + esc(t('data.m3')) + '</li></ol>') +
      sec('data.what_h', p(t('data.what', {pax: num(m.passengers), days: days, daily: num(L.D_daily)})) +
        p(t('data.share', {pct: pct(100 * L.D_daily / R.central), riders: num(R.central)})) +
        p(t('data.e', {c: num(E.central), l: num(E.low), h: num(E.high)}))) +
      sec('data.missing_h', p(t('data.missing'))) +
      sec('data.match_h', '<dl class="figs">' + fig('data.f.route', pct(m.route_matched_pct) + '%') + fig('data.f.both', pct(m.both_stops_pct_of_routed) + '%') +
        fig('data.f.order', pct(m.in_order_pct_of_both) + '%') + fig('data.f.usable', pct(m.usable_pct_of_all) + '%') + '</dl>') +
      sec('data.gps_h', '<dl class="figs two">' + fig('data.gps_board', num(bd.median_m) + ' m') + fig('data.gps_alight', num(al.median_m / 1000, 1) + ' km') + '</dl>' +
        p(t('data.gps', {n: num(b.matched), b: num(bd.median_m), a: num(al.median_m / 1000, 1)})) +
        p(t('data.gps_within', {p: pct(100 * bd.within_300m, 0)})) +
        (dw.total_ratio != null ? p(t('data.delivery', {r: pct(100 * dw.total_ratio, 0)}) + ((L.service || {}).from_gps ? ' ' + t('data.from_gps') : '')) : '') +
        (rpb != null ? p(t('data.rpb', {n: num(rpb)})) : '')) +
      sec('data.out_h', '<p class="cap">' + esc(t('data.levels')) + '</p>' + bar +
        p(t('data.over', {s: pct(L.over_seats_pct), t: pct(L.over_total_pct)})) +
        p(t('data.conf', {h: pct(conf.high), m: pct(conf.medium), l: pct(conf.low)})) +
        (L.censored_pct_of_cells != null ? p(t('data.censored', {p: pct(L.censored_pct_of_cells)})) : '') +
        p(t('data.hidden', {n: num((fl.low_n || 0) + (fl.gap || 0)), low: num(fl.low_n), gap: num(fl.gap)})) +
        (pk.am != null ? p(t('data.peaks', {am: pk.am, pm: pk.pm})) : '')) +
      sec('data.limits_h', '<ul class="limits"><li>' + esc(t('data.l1')) + '</li><li>' + esc(t('data.l2')) + '</li><li>' + esc(t('data.l3')) + '</li><li>' + esc(t('data.l4')) + '</li></ul>');
  }

  // First numeric value stored under key k anywhere in o, preferring a weekday branch.
  function deep(o, k) {
    if (!o || typeof o !== 'object') return null;
    if (typeof o[k] === 'number') return o[k];
    var keys = Object.keys(o).sort(function (a, b) { return (b === 'weekday') - (a === 'weekday'); });
    for (var i = 0; i < keys.length; i++) { var v = deep(o[keys[i]], k); if (v != null) return v; }
    return null;
  }

  function covStart() {
    if (cov.started && !cov.err) return;
    cov.started = true;
    cov.err = false;
    renderData();
    Data.coverage().then(function (c) { cov.res = c; renderData(); }, function () { cov.err = true; renderData(); });
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
    if (op.started) { hourOut(); renderTable(); renderProfile(); if (op.heat) $('#op-map-status').textContent = t('op.map_status', {n: num(op.heat.features.length), day: t('daytype.' + op.day), h: hr(op.hour) + '–' + hr(op.hour + 1)}); }
    if (cov.started) renderData();
  }

  // ---------- tabs ----------
  function tab(btn, focus) {
    $$('[role="tab"]').forEach(function (b) {
      var on = b === btn;
      b.setAttribute('aria-selected', on ? 'true' : 'false');
      b.tabIndex = on ? 0 : -1;
      $('#' + b.getAttribute('aria-controls')).hidden = !on;
    });
    s.tab = btn.id.replace('tab-', '');
    if (focus) btn.focus();
    var slot = s.tab === 'operator' ? '#op-mapslot' : s.tab === 'planner' ? '#plan-mapslot' : null;
    if (slot && $('#mapwrap').parentNode !== $(slot)) $(slot).appendChild($('#mapwrap'));
    legend();
    mode();
    if (s.tab === 'operator') opStart();
    if (s.tab === 'data') covStart();
    if (map && slot) requestAnimationFrame(function () {
      map.resize();
      if (s.tab === 'planner') draw();
      else if (op.keys.length) heatSel();
    });
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
      if (map) requestAnimationFrame(function () { map.resize(); if (s.tab === 'planner') draw(); });
    });

    // operator
    var timer = null;
    $('#op-day').addEventListener('change', function () {
      op.day = this.value;
      loadHeat();
      loadTop();
      if (op.prof) loadProfile(op.prof.row);
    });
    $('#op-hour').addEventListener('input', function () {
      op.hour = +this.value;
      hourOut();
      clearTimeout(timer);
      timer = setTimeout(loadHeat, 250);
    });
    $$('input[name="op-period"]').forEach(function (r) {
      r.addEventListener('change', function () { op.period = r.value; loadTop(); });
    });
    $('#op-table').addEventListener('click', function (e) {
      var sb = e.target.closest('[data-sort]');
      if (sb) {
        var k = sb.getAttribute('data-sort');
        op.sort = {k: k, d: op.sort.k === k ? -op.sort.d : (k === 'route' ? 1 : -1)};
        renderTable();
        $('[data-sort="' + k + '"]').focus();
        return;
      }
      var rb = e.target.closest('[data-row]');
      if (rb) { var key = rb.getAttribute('data-row'); pickRow(key); var nb = $('[data-row="' + CSS.escape(key) + '"]'); if (nb) nb.focus(); return; }
      if (e.target.closest('[data-op="retry"]')) loadTop();
    });
    $('#data-body').addEventListener('click', function (e) { if (e.target.closest('[data-cov="retry"]')) covStart(); });
    var rt = null;
    addEventListener('resize', function () { clearTimeout(rt); rt = setTimeout(function () { if (op.prof && s.tab === 'operator') renderProfile(); }, 200); });
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
