/* Level 7 — analyze your own games blindfolded. */
(function () {
  'use strict';
  const h = App.h;

  App.register({
    id: 'analyze',
    num: 7,
    short: 'Your games',
    title: 'Analyze your games blindfolded',
    defaultBlindfold: 'full',
    blurb: 'Load a game, then walk through it in your head. <b>Recall</b> makes you name every move ' +
      'before it is played; <b>Analyze</b> lets you branch off and calculate lines without a board.',
    mount: function (ctx) {
      const board = ctx.board;
      const statKey = 'l7';

      let games = [], parsed = null, mainline = [], idx = 0, game = null;
      let mode = 'analyze';                 // 'analyze' | 'recall'
      let variation = [], recallRight = 0, recallAsked = 0, myColor = 'w';

      /* ---------- sources ---------- */
      const userInput = h('input', {
        type: 'text', placeholder: 'lichess username', autocomplete: 'off',
        value: App.settings.lichessUser || ''
      });
      const maxSel = h('select', [
        h('option', { value: '20', text: 'last 20' }),
        h('option', { value: '50', text: 'last 50' }),
        h('option', { value: '100', text: 'last 100' })
      ]);
      const loadBtn = h('button.btn.primary', { text: 'Load games', onclick: loadFromLichess });
      const cacheBtn = h('button.btn', { text: 'Use saved games', onclick: useCache });
      const status = h('div.hint');
      const pgnBox = h('textarea', { rows: '4', placeholder: '…or paste a PGN here' });
      const pgnBtn = h('button.btn', { text: 'Use pasted PGN', onclick: usePasted });
      const gameUl = h('ul.list');

      /* ---------- play area ---------- */
      const title = h('div.prompt.small', { text: 'load a game →' });
      const sub = h('div.sub-prompt');
      const movesEl = h('div.movelist');
      const feedback = h('div.feedback');
      const engineEl = h('div.hint');
      const statsEl = h('div.stats');
      const input = h('input', { type: 'text', placeholder: 'move', autocomplete: 'off', spellcheck: 'false' });
      const form = h('form.move-input', {
        onsubmit: function (e) { e.preventDefault(); submit(input.value); input.value = ''; }
      }, [input, h('button.btn.primary', { type: 'submit', text: 'Enter' })]);

      const modeChips = h('div.tag-row', [
        chip('Analyze', 'analyze'), chip('Recall', 'recall')
      ]);

      function chip(label, id) {
        const c = h('span.chip', {
          text: label,
          onclick: function () {
            mode = id;
            Array.prototype.forEach.call(modeChips.children, function (x) { x.classList.toggle('on', x.textContent === label); });
            resetTo(0);
          }
        });
        if (id === 'analyze') c.classList.add('on');
        return c;
      }

      ctx.root.appendChild(h('div', [
        h('div.controls', [userInput, maxSel, loadBtn, cacheBtn]),
        h('p.hint', { text: 'One lichess export at a time per IP — if it says you are rate limited, ' +
          'wait a minute or use the saved copy.' }),
        h('div', { style: { marginTop: '8px' } }, [pgnBox]),
        h('div.controls', [pgnBtn]),
        status,
        gameUl,
        h('div.divider'),
        modeChips,
        title, sub,
        h('div', { style: { margin: '8px 0' } }, [movesEl]),
        form, feedback, engineEl,
        h('div.controls', { style: { marginTop: '10px' } }, [
          h('button.btn', { text: '◀ back', onclick: function () { step(-1); } }),
          h('button.btn', { text: 'forward ▶', onclick: function () { step(1); } }),
          h('button.btn', { text: 'Start', onclick: function () { resetTo(0); } }),
          h('button.btn', { text: 'Engine check', onclick: engineCheck }),
          h('button.btn', { text: 'Leave variation', onclick: leaveVariation })
        ]),
        h('p.hint', { html: 'Arrow keys step through the game. In <b>Analyze</b> mode, typing a move you ' +
          'did <i>not</i> play starts a variation you can calculate in your head; leave it to snap back.' }),
        h('div.divider'),
        statsEl
      ]));

      /* ---------- loading ---------- */

      function say(text, bad) {
        status.className = bad ? 'feedback err' : 'hint';
        status.textContent = text;
      }

      function useCache() {
        const user = userInput.value.trim();
        if (!user) { say('Enter a lichess username.', true); return; }
        const cached = Lichess.cachedGames(user);
        if (!cached || !cached.games.length) {
          say('Nothing saved for ' + user + ' yet — load them once first.', true);
          return;
        }
        games = cached.games;
        showGames(user);
        const age = Math.round((Date.now() - cached.at) / 60000);
        say(games.length + ' saved games (' + (age < 1 ? 'just now' : age + ' min old') + ').');
      }

      function loadFromLichess() {
        const user = userInput.value.trim();
        if (!user) { say('Enter a lichess username.', true); return; }
        App.settings.lichessUser = user;
        App.save();
        loadBtn.disabled = true;
        Lichess.fetchGames({
          user: user,
          max: parseInt(maxSel.value, 10),
          onStatus: function (msg) { say(msg); }
        })
          .then(function (list) { games = list; showGames(user); })
          .catch(function (err) {
            const cached = Lichess.cachedGames(user);
            if (cached && cached.games.length) {
              games = cached.games;
              showGames(user);
              say('Using ' + games.length + ' saved games instead — ' + err.message, true);
            } else {
              say(err.message, true);
            }
          })
          .then(function () { loadBtn.disabled = false; });
      }

      function usePasted() {
        const text = pgnBox.value.trim();
        if (!text) return;
        games = Lichess.splitGames(text).map(function (pgn) {
          const p = PGN.parse(pgn);
          return { pgn: pgn, headers: p.headers, root: p.root, parsedOk: p.errors.length === 0 };
        });
        showGames(null);
      }

      function showGames(user) {
        status.className = 'hint';
        if (!games.length) { status.textContent = 'No games found.'; return; }
        status.textContent = games.length + ' games loaded.';
        gameUl.innerHTML = '';
        games.slice(0, 60).forEach(function (g) {
          const hd = g.headers;
          const label = (hd.White || 'White') + ' – ' + (hd.Black || 'Black');
          const meta = [hd.Result || '', hd.Opening || hd.ECO || '', (hd.Date || hd.UTCDate || '').slice(0, 10)]
            .filter(Boolean).join(' · ');
          gameUl.appendChild(h('li', {
            onclick: function () {
              Array.prototype.forEach.call(gameUl.children, function (c) { c.classList.remove('active'); });
              this.classList.add('active');
              openGame(g, user);
            }
          }, [h('span', { text: label }), h('small', { text: meta })]));
        });
      }

      function openGame(g, user) {
        parsed = g;
        mainline = PGN.mainline(g.root);
        myColor = user ? (Lichess.playerColor(g.headers, user) || 'w') : 'w';
        title.textContent = (g.headers.White || 'White') + ' – ' + (g.headers.Black || 'Black') +
          '  ' + (g.headers.Result || '');
        sub.textContent = [g.headers.Event, g.headers.Opening, mainline.length + ' plies']
          .filter(Boolean).join(' · ');
        board.setOrientation(myColor);
        recallRight = 0;
        recallAsked = 0;
        resetTo(0);
      }

      /* ---------- navigation ---------- */

      function resetTo(n) {
        if (!parsed) return;
        variation = [];
        idx = Math.max(0, Math.min(n, mainline.length));
        game = new Chess(parsed.root.fenAfter || Chess.DEFAULT_FEN);
        for (let i = 0; i < idx; i++) game.move(mainline[i].san);
        feedback.textContent = '';
        engineEl.textContent = '';
        syncBoard(false);
        promptNext();
      }

      function step(dir) {
        if (!parsed || variation.length) return;
        if (dir > 0) {
          if (idx >= mainline.length) return;
          if (mode === 'recall') { feedback.className = 'feedback'; feedback.textContent = 'Name the move first.'; return; }
          const done = game.move(mainline[idx].san);
          idx++;
          syncBoard(true, done);
        } else {
          if (idx === 0) return;
          game.undo();
          idx--;
          syncBoard(true);
        }
        promptNext();
      }

      function promptNext() {
        if (!parsed) return;
        if (mode === 'recall' && idx < mainline.length) {
          const num = Math.floor(idx / 2) + 1;
          const who = (idx % 2 === 0) ? 'White' : 'Black';
          feedback.className = 'feedback info';
          feedback.textContent = 'Move ' + num + ', ' + who + ' to play — what was played?';
        } else if (idx >= mainline.length) {
          feedback.className = 'feedback';
          feedback.textContent = 'End of game.';
        }
        renderMoves();
        render();
      }

      function syncBoard(animate, done) {
        board.setPosition(game, {
          animate: animate !== false,
          lastMove: done ? [done.from, done.to] : (game.lastMove() ? [game.lastMove().from, game.lastMove().to] : null)
        });
        board.setMovable({
          color: 'both', dests: game.destinationsMap(),
          onMove: function (from, to) { submit(from + to); }
        });
        board.opts.viewOnly = false;
        renderMoves();
      }

      /* ---------- input ---------- */

      function submit(text) {
        if (!parsed) return;
        const value = String(text).trim();
        if (!value) return;
        const found = game.findMove(value);
        if (!found) {
          feedback.className = 'feedback err';
          feedback.textContent = '"' + value + '" is not legal in this position.';
          return;
        }
        const san = game.moveToSan(found, game.generateMoves());

        if (variation.length || mode === 'analyze') {
          const actual = (idx < mainline.length) ? mainline[idx].san : null;
          const done = game.move(san);
          if (san === actual && !variation.length) {
            idx++;
            feedback.className = 'feedback ok';
            feedback.textContent = '✓ ' + san + ' — that is the game move.';
          } else {
            variation.push(san);
            feedback.className = 'feedback info';
            feedback.textContent = 'Variation: ' + variation.join(' ') +
              (actual ? '   (game went ' + actual + ')' : '');
          }
          syncBoard(true, done);
          promptNext();
          return;
        }

        /* recall mode */
        if (idx >= mainline.length) return;
        const actual = mainline[idx].san;
        recallAsked++;
        if (san === actual) {
          recallRight++;
          const done = game.move(san);
          idx++;
          feedback.className = 'feedback ok';
          feedback.textContent = '✓ ' + san;
          App.stat(statKey, { asked: 1, right: 1 });
          syncBoard(true, done);
          promptNext();
        } else {
          feedback.className = 'feedback err';
          feedback.textContent = '✗ ' + san + ' — not what was played. Try again, or press ▶ after a peek.';
          App.stat(statKey, { asked: 1 });
          render();
        }
      }

      function leaveVariation() {
        if (!variation.length) return;
        for (let i = 0; i < variation.length; i++) game.undo();
        variation = [];
        feedback.className = 'feedback';
        feedback.textContent = 'Back to the game.';
        syncBoard(true);
        promptNext();
      }

      function engineCheck() {
        if (!game) return;
        engineEl.textContent = 'analyzing…';
        Ai.reply(game, { movetime: 900, depth: 5, timeMs: 2500, useTablebase: false }).then(function (res) {
          if (!res) { engineEl.textContent = 'no engine available'; return; }
          const score = (typeof res.scoreCp === 'number') ? (res.scoreCp / 100).toFixed(2) : null;
          engineEl.textContent = 'Engine (' + res.source + ') likes ' + (res.san || res.from + res.to) +
            (res.mateIn ? ' — mate in ' + Math.abs(res.mateIn) : (score !== null ? ' — eval ' + score : ''));
        });
      }

      function renderMoves() {
        movesEl.innerHTML = '';
        if (!parsed) return;
        const hideAhead = (mode === 'recall');
        PGN.rows(mainline.map(function (n) { return n.san; })).forEach(function (row, i) {
          movesEl.appendChild(h('span.num', { text: row.num + '.' }));
          [row.white, row.black].forEach(function (san, j) {
            const ply = i * 2 + j;
            const played = ply < idx;
            const cls = 'mv' + (ply === idx - 1 ? ' current' : '') +
              ((hideAhead && !played) ? ' hidden-move' : '');
            movesEl.appendChild(h('span', { class: cls, text: san || '' }));
          });
        });
        if (variation.length) {
          movesEl.appendChild(h('span.num', { text: '»' }));
          movesEl.appendChild(h('span.mv', { text: variation.join(' '), style: { gridColumn: 'span 2' } }));
        }
        movesEl.scrollTop = movesEl.scrollHeight;
      }

      function render() {
        const s = App.stat(statKey);
        statsEl.innerHTML = '';
        if (mode === 'recall') {
          statsEl.appendChild(h('span', {
            html: 'this game <b>' + recallRight + '/' + recallAsked + '</b>'
          }));
        }
        if (s.asked) {
          statsEl.appendChild(h('span', {
            html: 'all time <b>' + (s.right || 0) + '/' + s.asked + '</b> (' +
              Math.round(((s.right || 0) / s.asked) * 100) + '%)'
          }));
        }
        statsEl.appendChild(h('span', { html: 'ply <b>' + idx + '</b>' + (parsed ? ' of ' + mainline.length : '') }));
      }

      function onKey(e) {
        const tag = (e.target.tagName || '').toLowerCase();
        if (tag === 'input' || tag === 'textarea') return;
        if (e.key === 'ArrowRight') { e.preventDefault(); step(1); }
        else if (e.key === 'ArrowLeft') { e.preventDefault(); step(-1); }
      }
      document.addEventListener('keydown', onKey);

      const cachedUser = App.settings.lichessUser;
      if (cachedUser) {
        const cached = Lichess.cachedGames(cachedUser);
        if (cached && cached.games.length) {
          games = cached.games;
          showGames(cachedUser);
          status.textContent = games.length + ' cached games for ' + cachedUser + ' — reload for the latest.';
        }
      }

      render();
      return function () {
        document.removeEventListener('keydown', onKey);
        board.opts.viewOnly = true;
      };
    }
  });
})();
