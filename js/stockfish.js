/* Optional Stockfish backend.
 * Loads js/vendor/stockfish.js in a Web Worker when the page is served over http(s).
 * Browsers refuse workers from file:// URLs, so opening index.html directly falls back
 * to the small built-in search in js/ai.js — everything still works, just weaker. */
(function (global) {
  'use strict';

  const SCRIPT_SRC = (document.currentScript && document.currentScript.src) || '';
  const BASE = SCRIPT_SRC ? SCRIPT_SRC.replace(/\/js\/stockfish\.js.*$/, '/') : '';

  let worker = null;
  let ready = false;
  let booting = null;
  let queue = [];
  let lastError = null;

  function supported() {
    return typeof Worker === 'function' && location.protocol !== 'file:';
  }

  function boot() {
    if (booting) return booting;
    if (!supported()) {
      lastError = (location.protocol === 'file:')
        ? 'Stockfish needs the page to be served over http (run: py -m http.server)'
        : 'Web Workers unavailable';
      booting = Promise.resolve(false);
      return booting;
    }
    booting = new Promise(function (resolve) {
      try {
        worker = new Worker(BASE + 'js/vendor/stockfish.js');
      } catch (e) {
        lastError = e.message;
        resolve(false);
        return;
      }
      const timeout = setTimeout(function () {
        if (!ready) { lastError = 'Stockfish did not start in time'; resolve(false); }
      }, 12000);

      worker.onmessage = function (e) {
        const text = (typeof e.data === 'string') ? e.data : (e.data && e.data.data) || '';
        if (text.indexOf('uciok') === 0 || text === 'uciok') {
          worker.postMessage('isready');
        } else if (text.indexOf('readyok') > -1 && !ready) {
          ready = true;
          clearTimeout(timeout);
          resolve(true);
        }
        queue.forEach(function (fn) { fn(text); });
      };
      worker.onerror = function (err) {
        lastError = err.message || 'worker error';
        clearTimeout(timeout);
        resolve(false);
      };
      worker.postMessage('uci');
    });
    return booting;
  }

  function listen(fn) {
    queue.push(fn);
    return function () { queue = queue.filter(function (f) { return f !== fn; }); };
  }

  function send(cmd) { if (worker) worker.postMessage(cmd); }

  /* opts: { movetime (ms), depth, skill (0-20), multipv } -> { uci, san, ponder, info } */
  function bestMove(game, opts) {
    opts = opts || {};
    return boot().then(function (ok) {
      if (!ok) return null;
      return new Promise(function (resolve) {
        let info = { depth: null, scoreCp: null, mateIn: null, pv: null };
        const stop = listen(function (text) {
          if (text.indexOf('info') === 0 && text.indexOf(' pv ') > -1) {
            const d = text.match(/ depth (\d+)/);
            const cp = text.match(/score cp (-?\d+)/);
            const mate = text.match(/score mate (-?\d+)/);
            const pv = text.match(/ pv (.+)$/);
            if (d) info.depth = parseInt(d[1], 10);
            if (cp) info.scoreCp = parseInt(cp[1], 10);
            if (mate) info.mateIn = parseInt(mate[1], 10);
            if (pv) info.pv = pv[1].trim().split(/\s+/);
          } else if (text.indexOf('bestmove') === 0) {
            stop();
            const parts = text.split(/\s+/);
            const uci = parts[1];
            if (!uci || uci === '(none)') { resolve(null); return; }
            let san = null;
            try {
              const probe = game.clone();
              const mv = probe.move(uci);
              san = mv ? mv.san : null;
            } catch (e) { /* ignore */ }
            resolve({
              uci: uci,
              from: uci.slice(0, 2),
              to: uci.slice(2, 4),
              promotion: uci.length > 4 ? uci[4] : null,
              san: san,
              depth: info.depth,
              scoreCp: info.scoreCp,
              mateIn: info.mateIn,
              pv: info.pv,
              engine: 'stockfish'
            });
          }
        });

        if (typeof opts.skill === 'number') {
          send('setoption name Skill Level value ' + Math.max(0, Math.min(20, opts.skill)));
        }
        send('position fen ' + game.fen());
        send(opts.depth ? ('go depth ' + opts.depth) : ('go movetime ' + (opts.movetime || 600)));
      });
    });
  }

  global.Stockfish = {
    supported: supported,
    boot: boot,
    bestMove: bestMove,
    isReady: function () { return ready; },
    error: function () { return lastError; },
    stop: function () { send('stop'); }
  };
})(window);
