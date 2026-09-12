/* Level 3 — replay memorized opening theory blindfolded.
 * Two sources: the built-in lines, or an opening tree merged from your own lichess games. */
(function () {
  'use strict';
  const h = App.h;

  App.register({
    id: 'openings',
    num: 3,
    short: 'Openings',
    title: 'Review memorized opening theory',
    defaultBlindfold: 'pieces',
    blurb: 'Play your side of the line from memory. The opponent will sometimes deviate — ' +
      'punish it. Type moves in notation (<code>Nf3</code>, <code>exd5</code>, <code>O-O</code>, <code>g1f3</code>).',
    mount: function (ctx) {
      const board = ctx.board;
      const statKey = 'l3';

      let source = 'builtin';          // 'builtin' | 'lichess'
      let line = null;                 // { name, side, root, weighted }
      let game = null, node = null, mySide = 'w', finished = false;
      let errorsThisLine = 0, movesThisLine = 0, awaitingRetry = null;
      let repertoire = null, repGames = null, openingList = [];

      /* ---------- panel ---------- */
      const srcTabs = h('div.tag-row');
      const listBox = h('div');
      const lichessBox = h('div', { style: { display: 'none' } });

      const lineTitle = h('div.prompt.small', { text: 'pick a line →' });
      const lineNote = h('div.sub-prompt');
      const movesEl = h('div.movelist');
      const feedback = h('div.feedback');
      const input = h('input', { type: 'text', placeholder: 'your move', autocomplete: 'off', spellcheck: 'false' });
      const form = h('form.move-input', {
        onsubmit: function (e) { e.preventDefault(); submit(input.value); input.value = ''; }
      }, [input, h('button.btn.primary', { type: 'submit', text: 'Play' })]);
      const statsEl = h('div.stats');
      const hideMoves = h('input', { type: 'checkbox' });

      const playArea = h('div', [
        lineTitle, lineNote,
        h('div', { style: { margin: '8px 0' } }, [movesEl]),
        form, feedback,
        h('div.controls', { style: { marginTop: '10px' } }, [
          h('button.btn', { text: 'Hint', onclick: hint }),
          h('button.btn', { text: 'Show move', onclick: showMove }),
          h('button.btn', { text: 'Restart', onclick: function () { if (line) startLine(line); } }),
          h('label.check', [hideMoves, 'hide move list'])
        ]),
        h('div.divider'),
        statsEl
      ]);

      hideMoves.addEventListener('change', renderMoves);

      ctx.root.appendChild(h('div', [srcTabs, listBox, lichessBox, h('div.divider'), playArea]));

      function tab(name, id) {
        return h('span.chip', {
          text: name,
          onclick: function () {
            source = id;
            Array.prototype.forEach.call(srcTabs.children, function (c) { c.classList.toggle('on', c.textContent === name); });
            listBox.style.display = id === 'builtin' ? '' : 'none';
            lichessBox.style.display = id === 'lichess' ? '' : 'none';
          }
        });
      }
      const t1 = tab('Built-in theory', 'builtin');
      t1.classList.add('on');
      srcTabs.appendChild(t1);
      srcTabs.appendChild(tab('My lichess games', 'lichess'));

      /* ---------- built-in list ---------- */
      const ul = h('ul.list');
      window.OPENINGS.forEach(function (o) {
        const li = h('li', {
          onclick: function () {
            Array.prototype.forEach.call(ul.children, function (c) { c.classList.remove('active'); });
            li.classList.add('active');
            const parsed = PGN.parse(o.pgn);
            startLine({
              id: o.id, name: o.name, note: o.note, side: o.side,
              root: parsed.root, weighted: false, startFen: parsed.startFen
            });
          }
        }, [h('span', { text: o.name }), h('small', { text: o.eco + ' · ' + (o.side === 'w' ? 'White' : 'Black') })]);
        ul.appendChild(li);
      });
      listBox.appendChild(ul);

      /* ---------- lichess panel ---------- */
      const userInput = h('input', {
        type: 'text', placeholder: 'lichess username', autocomplete: 'off',
        value: App.settings.lichessUser || ''
      });
      const maxSel = h('select', [
        h('option', { value: '30', text: '30 games' }),
        h('option', { value: '50', text: '50 games' }),
        h('option', { value: '100', text: '100 games' }),
        h('option', { value: '200', text: '200 games' })
      ]);
      maxSel.value = '50';
      const colorSel = h('select', [
        h('option', { value: 'w', text: 'as White' }),
        h('option', { value: 'b', text: 'as Black' })
      ]);
      const depthSel = h('select', [
        h('option', { value: '10', text: '5 moves deep' }),
        h('option', { value: '16', text: '8 moves deep' }),
        h('option', { value: '24', text: '12 moves deep' })
      ]);
      depthSel.value = '16';
      const minSel = h('select', [
        h('option', { value: '1', text: 'all lines' }),
        h('option', { value: '2', text: 'played 2+ times' }),
        h('option', { value: '3', text: 'played 3+ times' })
      ]);
      minSel.value = '2';
      const loadBtn = h('button.btn.primary', { text: 'Load games', onclick: loadLichess });
      const cacheBtn = h('button.btn', { text: 'Use saved games', onclick: useCache });
      const tokenInput = h('input', {
        type: 'password', placeholder: 'API token (optional)', autocomplete: 'off',
        value: Lichess.token()
      });
      const lichessStatus = h('div.hint');
      const openingUl = h('ul.list');

      lichessBox.appendChild(h('div', [
        h('p.hint', { text: 'Pull your games from lichess and drill the openings you actually play. ' +
          'Opponent replies are sampled from what your opponents really played.' }),
        h('div.controls', [userInput, loadBtn, cacheBtn]),
        h('div.controls', { style: { marginTop: '8px' } }, [maxSel, colorSel, depthSel, minSel]),
        h('div.controls', { style: { marginTop: '8px' } }, [tokenInput]),
        h('p.hint', { html: 'Lichess allows one export at a time per IP; a second request gets a ' +
          'one-minute cooldown. Games are saved locally, so <b>Use saved games</b> re-drills them ' +
          'without touching the network. A personal API token (lichess.org → Preferences → API access ' +
          'tokens, no scopes needed) raises the limit.' }),
        lichessStatus,
        openingUl
      ]));

      function status(text, bad) {
        lichessStatus.className = bad ? 'feedback err' : 'hint';
        lichessStatus.textContent = text;
      }

      function useCache() {
        const user = userInput.value.trim();
        if (!user) { status('Enter a lichess username first.', true); return; }
        const cached = Lichess.cachedGames(user);
        if (!cached || !cached.games.length) {
          status('Nothing saved for ' + user + ' yet — load them once first.', true);
          return;
        }
        repGames = cached.games;
        buildTree(user);
        const age = Math.round((Date.now() - cached.at) / 60000);
        status(cached.games.length + ' saved games (' + (age < 1 ? 'just now' : age + ' min old') + ').');
      }

      function loadLichess() {
        const user = userInput.value.trim();
        if (!user) { status('Enter a lichess username first.', true); return; }
        App.settings.lichessUser = user;
        App.save();
        Lichess.setToken(tokenInput.value);
        loadBtn.disabled = true;
        Lichess.fetchGames({
          user: user,
          max: parseInt(maxSel.value, 10),
          color: colorSel.value === 'w' ? 'white' : 'black',
          onStatus: function (msg) { status(msg); }
        })
          .then(function (games) {
            repGames = games;
            buildTree(user);
          })
          .catch(function (err) {
            const cached = Lichess.cachedGames(user);
            if (cached && cached.games.length) {
              repGames = cached.games;
              buildTree(user);
              status('Using ' + cached.games.length + ' saved games instead — ' + err.message, true);
            } else {
              status(err.message, true);
            }
          })
          .then(function () { loadBtn.disabled = false; });
      }

      function buildTree(user) {
        repertoire = Lichess.buildRepertoire(repGames, {
          user: user,
          color: colorSel.value,
          maxPly: parseInt(depthSel.value, 10),
          minCount: parseInt(minSel.value, 10)
        });
        openingList = Lichess.openingSummary(repertoire);
        lichessStatus.className = 'hint';
        lichessStatus.textContent = repertoire.gamesUsed + ' games as ' +
          (colorSel.value === 'w' ? 'White' : 'Black') + ' · ' + openingList.length + ' openings.';
        openingUl.innerHTML = '';
        openingUl.appendChild(h('li', {
          onclick: function () { trainRep(null, 'Everything I play as ' + (colorSel.value === 'w' ? 'White' : 'Black')); }
        }, [h('span', { text: 'All my games' }), h('small', { text: repertoire.gamesUsed + ' games' })]));
        openingList.slice(0, 30).forEach(function (o) {
          openingUl.appendChild(h('li', {
            onclick: function () { trainRep(o.name, o.name); }
          }, [h('span', { text: o.name }), h('small', { text: o.count + '×' })]));
        });
      }

      function trainRep(openingName, title) {
        const tree = openingName ? Lichess.filterByOpening(repertoire, openingName) : repertoire;
        startLine({
          id: 'lichess:' + (openingName || 'all'),
          name: title,
          note: 'From your own games — the reply you are expected to find is the move you played most often.',
          side: colorSel.value,
          root: tree,
          weighted: true,
          startFen: Chess.DEFAULT_FEN
        });
      }

      /* ---------- tree adapters ---------- */
      function childrenOf(n) {
        if (!n) return [];
        if (Array.isArray(n.children)) {
          return n.children.map(function (c, i) { return { san: c.san, node: c, weight: i === 0 ? 3 : 1 }; });
        }
        return Lichess.kids(n).map(function (c) { return { san: c.san, node: c, weight: c.count }; });
      }

      function pickChild(list) {
        let total = 0;
        list.forEach(function (c) { total += c.weight; });
        let r = Math.random() * total;
        for (let i = 0; i < list.length; i++) { r -= list[i].weight; if (r <= 0) return list[i]; }
        return list[0];
      }

      /* ---------- play ---------- */
      function startLine(l) {
        line = l;
        mySide = l.side;
        game = new Chess(l.startFen || Chess.DEFAULT_FEN);
        node = l.root;
        finished = false;
        errorsThisLine = 0;
        movesThisLine = 0;
        awaitingRetry = null;
        lineTitle.textContent = l.name;
        lineNote.textContent = l.note || '';
        feedback.textContent = '';
        board.setOrientation(mySide);
        App.settings.orientation = mySide;
        board.setPosition(game, { animate: false, lastMove: null });
        board.setMovable({
          color: mySide, dests: game.destinationsMap(),
          onMove: function (from, to) { submit(from + to); }
        });
        board.opts.viewOnly = false;
        renderMoves();
        if (game.turnColor() !== mySide) setTimeout(opponentMove, 350);
        input.focus();
        render();
      }

      function opponentMove() {
        const list = childrenOf(node);
        if (!list.length) { endLine(true); return; }
        const chosen = pickChild(list);
        applyMove(chosen.san, chosen.node);
        feedback.className = 'feedback info';
        const num = Math.ceil(game.history.length / 2);
        feedback.textContent = 'Opponent: ' + num + (game.turnColor() === 'b' ? '. ' : '... ') + chosen.san +
          (list.length > 1 ? '  (one of ' + list.length + ' they have played)' : '');
        if (!childrenOf(node).length) endLine(true);
        input.focus();
      }

      function applyMove(san, newNode) {
        const done = game.move(san);
        node = newNode;
        board.setPosition(game, { animate: true, lastMove: done ? [done.from, done.to] : null });
        board.setMovable({
          color: mySide, dests: game.destinationsMap(),
          onMove: function (from, to) { submit(from + to); }
        });
        renderMoves();
      }

      function submit(text) {
        if (!line || finished) return;
        if (game.turnColor() !== mySide) return;
        const value = String(text).trim();
        if (!value) return;

        const candidates = childrenOf(node);
        const legal = game.findMove(value);
        if (!legal) {
          feedback.className = 'feedback err';
          feedback.textContent = '"' + value + '" is not legal here.';
          return;
        }
        const san = game.moveToSan(legal, game.generateMoves());
        const match = candidates.find(function (c) { return c.san === san; });
        movesThisLine++;

        if (match) {
          const best = candidates.slice().sort(function (a, b) { return b.weight - a.weight; })[0];
          feedback.className = 'feedback ok';
          feedback.textContent = '✓ ' + san +
            (match !== best && line.weighted ? '  (you usually play ' + best.san + ')' : '');
          App.stat(statKey, { moves: 1, right: 1 });
          applyMove(san, match.node);
          if (!childrenOf(node).length) { endLine(true); return; }
          setTimeout(opponentMove, 420);
        } else {
          errorsThisLine++;
          App.stat(statKey, { moves: 1 });
          feedback.className = 'feedback err';
          const expected = candidates.map(function (c) { return c.san; }).join(' / ');
          feedback.textContent = '✗ ' + san + ' — ' + (candidates.length ?
            'the line goes ' + expected : 'the line ends here') + '. Try again.';
          awaitingRetry = san;
        }
        render();
      }

      function hint() {
        const candidates = childrenOf(node);
        if (!candidates.length || game.turnColor() !== mySide) return;
        const best = candidates.slice().sort(function (a, b) { return b.weight - a.weight; })[0];
        const s = best.san;
        feedback.className = 'feedback info';
        feedback.textContent = 'Hint: ' + (/^[NBRQK]/.test(s) ? Chess.PIECE_NAMES[s[0].toLowerCase()] : 'Pawn') +
          ' move, ' + s.length + ' characters, starts with "' + s[0] + '".';
        App.stat(statKey, { hints: 1 });
      }

      function showMove() {
        const candidates = childrenOf(node);
        if (!candidates.length || game.turnColor() !== mySide) return;
        const best = candidates.slice().sort(function (a, b) { return b.weight - a.weight; })[0];
        feedback.className = 'feedback info';
        feedback.textContent = 'The move is ' + best.san + '.';
        errorsThisLine++;
        App.stat(statKey, { shown: 1 });
      }

      function endLine(reached) {
        finished = true;
        board.setMovable({ color: null, dests: null, onMove: null });
        feedback.className = errorsThisLine ? 'feedback info' : 'feedback ok';
        feedback.textContent = reached
          ? 'End of line — ' + movesThisLine + ' of your moves, ' + errorsThisLine + ' slip' +
            (errorsThisLine === 1 ? '' : 's') + '.'
          : 'Line over.';
        App.stat(statKey, { lines: 1, clean: errorsThisLine === 0 ? 1 : 0 });
        render();
      }

      function renderMoves() {
        movesEl.innerHTML = '';
        const sans = game ? game.historySan() : [];
        const hide = hideMoves.checked;
        PGN.rows(sans).forEach(function (row, i) {
          movesEl.appendChild(h('span.num', { text: row.num + '.' }));
          movesEl.appendChild(h('span', {
            class: 'mv' + (hide && i * 2 < sans.length - 1 ? ' hidden-move' : '') +
              (i * 2 === sans.length - 1 ? ' current' : ''),
            text: row.white
          }));
          movesEl.appendChild(h('span', {
            class: 'mv' + (hide && i * 2 + 1 < sans.length - 1 ? ' hidden-move' : '') +
              (i * 2 + 1 === sans.length - 1 ? ' current' : ''),
            text: row.black
          }));
        });
        movesEl.scrollTop = movesEl.scrollHeight;
      }

      function render() {
        const s = App.stat(statKey);
        statsEl.innerHTML = '';
        statsEl.appendChild(h('span', { html: 'this line <b>' + movesThisLine + '</b> moves, <b>' + errorsThisLine + '</b> errors' }));
        statsEl.appendChild(h('span', { html: 'lines finished <b>' + (s.lines || 0) + '</b>' }));
        statsEl.appendChild(h('span', { html: 'clean <b>' + (s.clean || 0) + '</b>' }));
        if (s.moves) {
          statsEl.appendChild(h('span', {
            html: 'accuracy <b>' + Math.round(((s.right || 0) / s.moves) * 100) + '%</b>'
          }));
        }
      }

      render();
      return function () { board.opts.viewOnly = true; };
    }
  });
})();
