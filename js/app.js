/* App shell: level routing, shared board, peek control, settings, stats. */
(function (global) {
  'use strict';

  /* ---------- tiny DOM helper ---------- */
  function h(tag, attrs, children) {
    const parts = tag.split('.');
    const e = document.createElement(parts[0]);
    if (parts.length > 1) e.className = parts.slice(1).join(' ');
    if (attrs && (typeof attrs !== 'object' || Array.isArray(attrs))) { children = attrs; attrs = null; }
    if (attrs) {
      Object.keys(attrs).forEach(function (k) {
        const v = attrs[k];
        if (v === null || v === undefined || v === false) return;
        if (k === 'class') e.className += (e.className ? ' ' : '') + v;
        else if (k === 'text') e.textContent = v;
        else if (k === 'html') e.innerHTML = v;
        else if (k === 'style' && typeof v === 'object') Object.assign(e.style, v);
        else if (k.slice(0, 2) === 'on') e.addEventListener(k.slice(2).toLowerCase(), v);
        else if (k === 'value') e.value = v;
        else e.setAttribute(k, v === true ? '' : v);
      });
    }
    (Array.isArray(children) ? children : (children === undefined || children === null ? [] : [children]))
      .forEach(function (c) {
        if (c === null || c === undefined || c === false) return;
        e.appendChild(typeof c === 'string' || typeof c === 'number' ? document.createTextNode(String(c)) : c);
      });
    return e;
  }

  /* ---------- persistence ---------- */
  const STORE_KEY = 'blindfold-trainer-v1';
  function loadStore() {
    try { return JSON.parse(localStorage.getItem(STORE_KEY)) || {}; } catch (e) { return {}; }
  }
  function saveStore(data) {
    try { localStorage.setItem(STORE_KEY, JSON.stringify(data)); } catch (e) { /* private mode */ }
  }

  const App = {
    levels: [],
    current: null,
    cleanup: null,
    store: loadStore(),
    h: h
  };

  App.settings = Object.assign({
    blindfold: {},          // per level id
    peekMode: 'hold',       // 'hold' | 'flash'
    peekSeconds: 2,
    orientation: 'w',
    animate: true,
    sound: false
  }, App.store.settings || {});

  App.save = function () {
    App.store.settings = App.settings;
    saveStore(App.store);
  };

  App.stat = function (key, patch) {
    App.store.stats = App.store.stats || {};
    const cur = App.store.stats[key] || {};
    if (patch) {
      Object.keys(patch).forEach(function (k) {
        cur[k] = (typeof patch[k] === 'number' && typeof cur[k] === 'number') ? cur[k] + patch[k] : patch[k];
      });
      App.store.stats[key] = cur;
      saveStore(App.store);
    }
    return cur;
  };

  App.resetStat = function (key) {
    App.store.stats = App.store.stats || {};
    delete App.store.stats[key];
    saveStore(App.store);
  };

  App.register = function (def) { App.levels.push(def); };

  /* ---------- toast ---------- */
  let toastEl = null, toastTimer = null;
  App.toast = function (msg, ms) {
    if (!toastEl) { toastEl = h('div.toast'); document.body.appendChild(toastEl); }
    toastEl.textContent = msg;
    toastEl.classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { toastEl.classList.remove('show'); }, ms || 1800);
  };

  /* ---------- peek ---------- */
  const peek = {
    active: false,
    count: 0,
    totalMs: 0,
    startedAt: 0,
    flashTimer: null,
    listeners: []
  };
  App.peek = peek;

  peek.onChange = function (fn) { peek.listeners.push(fn); };
  function notifyPeek() { peek.listeners.forEach(function (f) { f(peek); }); }

  peek.begin = function () {
    if (peek.active) return;
    if (!App.board || !App.board.isHidden()) return;
    peek.active = true;
    peek.count++;
    peek.startedAt = Date.now();
    App.board.setPeeking(true);
    if (App.current) App.stat('peeks-' + App.current.id, { count: 1 });
    notifyPeek();
  };

  peek.end = function () {
    if (!peek.active) return;
    peek.active = false;
    peek.totalMs += Date.now() - peek.startedAt;
    clearTimeout(peek.flashTimer);
    if (App.board) App.board.setPeeking(false);
    notifyPeek();
  };

  peek.flash = function (seconds) {
    peek.begin();
    clearTimeout(peek.flashTimer);
    peek.flashTimer = setTimeout(peek.end, (seconds || App.settings.peekSeconds) * 1000);
  };

  peek.trigger = function () {
    if (App.settings.peekMode === 'flash') peek.flash();
    else peek.begin();
  };

  peek.resetSession = function () {
    peek.end();
    peek.count = 0;
    peek.totalMs = 0;
    notifyPeek();
  };

  /* ---------- boot ---------- */

  App.boot = function () {
    /* Inside the Caissa workspace the URL belongs to the workspace router, so the
       trainer neither reads nor writes the hash. Standalone, it still deep-links. */
    App.embedded = !!document.getElementById('workspace');
    const nav = document.getElementById('levels');
    const boardHolder = document.getElementById('board');
    const controlsEl = document.getElementById('board-controls');
    const panel = document.getElementById('panel');

    App.board = new Board(boardHolder, {
      orientation: App.settings.orientation,
      animationMs: App.settings.animate ? 200 : 0,
      viewOnly: true
    });

    /* nav */
    App.levels.forEach(function (lvl) {
      const btn = h('button', { onclick: function () { App.go(lvl.id); } }, [
        h('span.num', { text: String(lvl.num) }), lvl.short
      ]);
      btn.dataset.level = lvl.id;
      nav.appendChild(btn);
    });

    /* shared board controls */
    const peekBtn = h('button.btn.peek', { text: 'Peek', title: 'Hold to reveal (or hold Space)' });
    peekBtn.addEventListener('pointerdown', function (e) {
      e.preventDefault();
      peek.trigger();
    });
    ['pointerup', 'pointerleave', 'pointercancel'].forEach(function (ev) {
      peekBtn.addEventListener(ev, function () { if (App.settings.peekMode === 'hold') peek.end(); });
    });

    const peekInfo = h('span.hint', { text: '' });
    const blindSel = h('select', {
      title: 'What to hide',
      onchange: function () {
        if (App.current) {
          App.settings.blindfold[App.current.id] = this.value;
          App.save();
          App.board.setBlindfold(this.value);
          updatePeekUi();
        }
      }
    }, [
      h('option', { value: 'pieces', text: 'Hide pieces' }),
      h('option', { value: 'full', text: 'Hide board' }),
      h('option', { value: 'off', text: 'Show all' })
    ]);
    App._blindSel = blindSel;

    const modeSel = h('select', {
      title: 'Peek behavior',
      onchange: function () { App.settings.peekMode = this.value; App.save(); updatePeekUi(); }
    }, [
      h('option', { value: 'hold', text: 'Peek: hold' }),
      h('option', { value: 'flash', text: 'Peek: flash' })
    ]);
    modeSel.value = App.settings.peekMode;

    const flipBtn = h('button.btn', {
      text: 'Flip',
      onclick: function () {
        App.board.toggleOrientation();
        App.settings.orientation = App.board.opts.orientation;
        App.save();
      }
    });

    controlsEl.appendChild(h('div.controls', [peekBtn, blindSel, modeSel, flipBtn, peekInfo]));

    function updatePeekUi() {
      peekBtn.classList.toggle('on', peek.active);
      peekBtn.disabled = App.board.opts.blindfold === 'off';   // nothing to reveal
      const secs = (peek.totalMs / 1000).toFixed(1);
      peekInfo.textContent = peek.count ? ('peeks: ' + peek.count + ' · ' + secs + 's') : '';
    }
    peek.onChange(updatePeekUi);
    App.updatePeekUi = updatePeekUi;

    /* space = peek */
    document.addEventListener('keydown', function (e) {
      if (e.code !== 'Space' || e.repeat) return;
      const tag = (e.target.tagName || '').toLowerCase();
      if (tag === 'input' || tag === 'textarea' || tag === 'select') return;
      e.preventDefault();
      peek.trigger();
    });
    document.addEventListener('keyup', function (e) {
      if (e.code !== 'Space') return;
      if (App.settings.peekMode === 'hold') peek.end();
    });
    window.addEventListener('blur', function () { if (App.settings.peekMode === 'hold') peek.end(); });

    App.panel = panel;
    const start = App.embedded ? App.levels[0].id
      : ((location.hash || '').replace('#', '') || App.levels[0].id);
    App.go(App.levels.some(function (l) { return l.id === start; }) ? start : App.levels[0].id);
  };

  App.go = function (id) {
    const lvl = App.levels.find(function (l) { return l.id === id; });
    if (!lvl) return;
    if (App.cleanup) { try { App.cleanup(); } catch (e) { console.error(e); } App.cleanup = null; }
    App.current = lvl;
    if (!App.embedded) location.hash = id;

    Array.prototype.forEach.call(document.querySelectorAll('nav.levels button'), function (b) {
      b.classList.toggle('active', b.dataset.level === id);
    });

    peek.resetSession();
    App.board.setMovable({ color: null, dests: null, onMove: null });
    App.board.opts.viewOnly = true;
    App.board.setShapes([]);
    App.board.setHighlights({});
    App.board.setLastMove(null);
    App.board.setCheck(null);

    const mode = App.settings.blindfold[id] || lvl.defaultBlindfold || 'pieces';
    App._blindSel.value = mode;
    App.board.setBlindfold(mode);

    App.panel.innerHTML = '';
    const header = h('div', [
      h('h2', { text: lvl.num + '. ' + lvl.title }),
      h('p.hint', { html: lvl.blurb })
    ]);
    const body = h('div');
    App.panel.appendChild(h('div.panel', [header, h('div.divider'), body]));

    App.cleanup = lvl.mount({ root: body, board: App.board, h: h, peek: peek }) || null;
    App.updatePeekUi();
  };

  /* shared helpers for levels */
  App.util = {
    randomSquare: function (filter) {
      const all = Chess.SQUARES.filter(filter || function () { return true; });
      return all[Math.floor(Math.random() * all.length)];
    },
    shuffle: function (arr) {
      const a = arr.slice();
      for (let i = a.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        const t = a[i]; a[i] = a[j]; a[j] = t;
      }
      return a;
    },
    fmtTime: function (ms) {
      const s = Math.max(0, Math.round(ms / 1000));
      return Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0');
    },
    knightMoves: function (sq) {
      const f = Chess.fileOf(sq), r = Chess.rankOf(sq), out = [];
      [[1, 2], [2, 1], [2, -1], [1, -2], [-1, -2], [-2, -1], [-2, 1], [-1, 2]].forEach(function (d) {
        const s = Chess.squareAt(f + d[0], r + d[1]);
        if (s) out.push(s);
      });
      return out;
    },
    bishopMoves: function (sq) {
      const f = Chess.fileOf(sq), r = Chess.rankOf(sq), out = [];
      [[1, 1], [1, -1], [-1, 1], [-1, -1]].forEach(function (d) {
        for (let i = 1; i < 8; i++) {
          const s = Chess.squareAt(f + d[0] * i, r + d[1] * i);
          if (!s) break;
          out.push(s);
        }
      });
      return out;
    },
    rookMoves: function (sq) {
      const f = Chess.fileOf(sq), r = Chess.rankOf(sq), out = [];
      [[1, 0], [-1, 0], [0, 1], [0, -1]].forEach(function (d) {
        for (let i = 1; i < 8; i++) {
          const s = Chess.squareAt(f + d[0] * i, r + d[1] * i);
          if (!s) break;
          out.push(s);
        }
      });
      return out;
    },
    /* breadth-first shortest route for a lone piece on an empty board */
    shortestPath: function (piece, from, to, blocked) {
      const movesFn = { n: App.util.knightMoves, b: App.util.bishopMoves, r: App.util.rookMoves }[piece];
      if (!movesFn) return null;
      if (from === to) return [from];
      const prev = {}, seen = {};
      seen[from] = true;
      let frontier = [from];
      while (frontier.length) {
        const next = [];
        for (const sq of frontier) {
          for (const cand of movesFn(sq)) {
            if (seen[cand] || (blocked && blocked.indexOf(cand) > -1)) continue;
            seen[cand] = true;
            prev[cand] = sq;
            if (cand === to) {
              const path = [to];
              let cur = to;
              while (prev[cur]) { cur = prev[cur]; path.unshift(cur); }
              return path;
            }
            next.push(cand);
          }
        }
        frontier = next;
      }
      return null;
    }
  };

  global.App = App;
  document.addEventListener('DOMContentLoaded', function () { App.boot(); });
})(window);
