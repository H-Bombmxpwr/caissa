/* Level 4 — theoretical endgames against real resistance. */
(function () {
  'use strict';
  const h = App.h;

  App.register({
    id: 'endgames',
    num: 4,
    short: 'Endgames',
    title: 'Practice endgame theory',
    defaultBlindfold: 'pieces',
    blurb: 'Play the winning (or drawing) technique out blindfolded. The defender plays the ' +
      'toughest defense available — the lichess tablebase when you are online.',
    mount: function (ctx) {
      const board = ctx.board;
      const statKey = 'l4';

      let spec = null, game = null, mySide = 'w', thinking = false, over = false;
      let plies = 0, startedAt = 0, bothSides = false;

      const title = h('div.prompt.small', { text: 'pick an ending →' });
      const note = h('div.sub-prompt');
      const statusEl = h('div.feedback');
      const movesEl = h('div.movelist');
      const engineEl = h('div.hint');
      const input = h('input', { type: 'text', placeholder: 'your move', autocomplete: 'off', spellcheck: 'false' });
      const form = h('form.move-input', {
        onsubmit: function (e) { e.preventDefault(); play(input.value); input.value = ''; }
      }, [input, h('button.btn.primary', { type: 'submit', text: 'Play' })]);
      const statsEl = h('div.stats');
      const bothBox = h('input', { type: 'checkbox', onchange: function () { bothSides = this.checked; } });

      const ul = h('ul.list');
      window.ENDGAMES.forEach(function (e) {
        const li = h('li', {
          onclick: function () {
            Array.prototype.forEach.call(ul.children, function (c) { c.classList.remove('active'); });
            li.classList.add('active');
            start(e);
          }
        }, [
          h('span', { text: e.name }),
          h('small', { text: (e.goal === 'draw' ? 'hold the draw' : e.goal === 'mate' ? 'mate' : 'win') + ' · par ' + e.par })
        ]);
        ul.appendChild(li);
      });

      ctx.root.appendChild(h('div', [
        ul,
        h('div.divider'),
        title, note,
        h('div', { style: { margin: '8px 0' } }, [movesEl]),
        form, statusEl, engineEl,
        h('div.controls', { style: { marginTop: '10px' } }, [
          h('button.btn', { text: 'Takeback', onclick: takeback }),
          h('button.btn', { text: 'Best move', onclick: showBest }),
          h('button.btn', { text: 'Restart', onclick: function () { if (spec) start(spec); } }),
          h('label.check', [bothBox, 'play both sides'])
        ]),
        h('div.divider'),
        statsEl
      ]));

      function start(e) {
        spec = e;
        game = new Chess(e.fen);
        mySide = e.you;
        over = false;
        plies = 0;
        startedAt = Date.now();
        title.textContent = e.name;
        note.textContent = e.note;
        statusEl.className = 'feedback';
        statusEl.textContent = e.goal === 'draw' ? 'Hold the draw.' :
          e.goal === 'mate' ? 'Force mate — par is about ' + e.par + ' moves.' :
          'Convert the win — par is about ' + e.par + ' moves.';
        engineEl.textContent = '';
        board.setOrientation(mySide);
        sync(false);
        render();
        input.focus();
      }

      function sync(animate, lastMove) {
        board.setPosition(game, { animate: animate !== false, lastMove: lastMove || null });
        const myTurn = bothSides || game.turnColor() === mySide;
        board.opts.viewOnly = !myTurn || over;
        board.setMovable(myTurn && !over ? {
          color: game.turnColor(), dests: game.destinationsMap(),
          onMove: function (from, to) { play(from + to); }
        } : { color: null, dests: null, onMove: null });
        renderMoves();
      }

      function renderMoves() {
        movesEl.innerHTML = '';
        const sans = game ? game.historySan() : [];
        PGN.rows(sans).forEach(function (row, i) {
          movesEl.appendChild(h('span.num', { text: row.num + '.' }));
          movesEl.appendChild(h('span.mv', { text: row.white, class: (i * 2 === sans.length - 1) ? 'current' : '' }));
          movesEl.appendChild(h('span.mv', { text: row.black, class: (i * 2 + 1 === sans.length - 1) ? 'current' : '' }));
        });
        movesEl.scrollTop = movesEl.scrollHeight;
      }

      function play(text) {
        if (!game || over || thinking) return;
        const value = String(text).trim();
        if (!value) return;
        if (!bothSides && game.turnColor() !== mySide) return;
        const done = game.move(value);
        if (!done) {
          statusEl.className = 'feedback err';
          statusEl.textContent = '"' + value + '" is not legal here.';
          return;
        }
        plies++;
        statusEl.className = 'feedback';
        statusEl.textContent = done.san;
        sync(true, [done.from, done.to]);
        if (checkOver()) return;
        if (!bothSides) setTimeout(respond, 260);
      }

      function respond() {
        if (over) return;
        thinking = true;
        engineEl.textContent = 'thinking…';
        Ai.reply(game, { movetime: 500, depth: 4, timeMs: 1500 }).then(function (res) {
          thinking = false;
          if (!res || over) { engineEl.textContent = ''; return; }
          const done = game.move(res.san || { from: res.from, to: res.to });
          if (!done) { engineEl.textContent = 'defense failed to move'; return; }
          plies++;
          sync(true, [done.from, done.to]);
          statusEl.className = 'feedback info';
          statusEl.textContent = 'Defense: ' + done.san;
          engineEl.textContent = 'defender: ' + ({
            tablebase: 'lichess tablebase (perfect)',
            stockfish: 'Stockfish',
            builtin: 'built-in search'
          })[res.source] + (res.category ? ' · position is ' + describe(res.category) : '') +
            (res.mateIn ? ' · mate in ' + res.mateIn : '');
          checkOver();
        });
      }

      function describe(category) {
        return ({ win: 'winning for the side to move', loss: 'lost for the side to move',
          draw: 'a draw', 'cursed-win': 'a win but past the 50-move rule',
          'blessed-loss': 'lost but saved by the 50-move rule' })[category] || category;
      }

      function checkOver() {
        if (!game) return false;
        let msg = null, good = false;
        if (game.isCheckmate()) {
          const winner = game.turnColor() === 'w' ? 'b' : 'w';
          good = winner === mySide;
          msg = good ? 'Checkmate — you did it in ' + Math.ceil(plies / 2) + ' moves (par ' + spec.par + ').'
                     : 'Checkmate against you.';
        } else if (game.isStalemate()) {
          good = spec.goal === 'draw';
          msg = good ? 'Stalemate — the draw is held.' : 'Stalemate! The win slipped away.';
        } else if (game.insufficientMaterial()) {
          good = spec.goal === 'draw';
          msg = good ? 'Insufficient material — drawn, as intended.' : 'Material gone — only a draw.';
        } else if (game.halfMoves >= 100) {
          good = spec.goal === 'draw';
          msg = good ? 'Fifty-move rule — draw held.' : 'Fifty moves without progress — drawn.';
        }
        if (!msg) return false;
        over = true;
        board.opts.viewOnly = true;
        board.setMovable({ color: null, dests: null, onMove: null });
        statusEl.className = good ? 'feedback ok' : 'feedback err';
        statusEl.textContent = msg;
        App.stat(statKey, { attempts: 1, solved: good ? 1 : 0 });
        const key = 'l4-' + spec.id;
        const prev = App.stat(key);
        if (good && (!prev.best || Math.ceil(plies / 2) < prev.best)) App.stat(key, { best: Math.ceil(plies / 2) });
        render();
        return true;
      }

      function takeback() {
        if (!game) return;
        game.undo();
        if (!bothSides) game.undo();
        over = false;
        plies = Math.max(0, plies - 2);
        statusEl.textContent = '';
        sync(true, game.lastMove() ? [game.lastMove().from, game.lastMove().to] : null);
      }

      function showBest() {
        if (!game || over) return;
        engineEl.textContent = 'looking…';
        Ai.reply(game, { movetime: 700, depth: 5, timeMs: 2500 }).then(function (res) {
          if (!res) { engineEl.textContent = ''; return; }
          engineEl.textContent = 'Best: ' + (res.san || (res.from + res.to)) +
            (res.mateIn ? ' (mate in ' + res.mateIn + ')' : '') + ' — from ' + res.source;
          App.stat(statKey, { hints: 1 });
        });
      }

      function render() {
        const s = App.stat(statKey);
        statsEl.innerHTML = '';
        statsEl.appendChild(h('span', { html: 'attempts <b>' + (s.attempts || 0) + '</b>' }));
        statsEl.appendChild(h('span', { html: 'successes <b>' + (s.solved || 0) + '</b>' }));
        if (spec) {
          const best = App.stat('l4-' + spec.id).best;
          if (best) statsEl.appendChild(h('span', { html: 'best here <b>' + best + ' moves</b>' }));
        }
        if (Stockfish.supported()) statsEl.appendChild(h('span', { text: 'Stockfish available' }));
      }

      render();
      return function () { over = true; board.opts.viewOnly = true; };
    }
  });
})();
