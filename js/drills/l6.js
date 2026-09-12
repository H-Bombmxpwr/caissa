/* Level 6 — endgame studies and visualization puzzles, solved blindfolded on the clock. */
(function () {
  'use strict';
  const h = App.h;

  App.register({
    id: 'studies',
    num: 6,
    short: 'Studies',
    title: 'Solve endgame studies',
    defaultBlindfold: 'full',
    blurb: 'Memorise the position, then solve it in your head. The clock starts when you open a study; ' +
      'twenty minutes is the classic allowance.',
    mount: function (ctx) {
      const board = ctx.board;
      const statKey = 'l6';

      let spec = null, game = null, node = null, mySide = 'w';
      let solved = false, failedMoves = 0, deadline = 0, tick = null;

      const title = h('div.prompt.small', { text: 'pick a study →' });
      const sub = h('div.sub-prompt');
      const setupEl = h('div.hint.mono', { style: { margin: '6px 0' } });
      const timerEl = h('div.timer');
      const movesEl = h('div.movelist');
      const feedback = h('div.feedback');
      const ideaEl = h('div.hint');
      const statsEl = h('div.stats');

      const input = h('input', { type: 'text', placeholder: 'your move', autocomplete: 'off', spellcheck: 'false' });
      const form = h('form.move-input', {
        onsubmit: function (e) { e.preventDefault(); play(input.value); input.value = ''; }
      }, [input, h('button.btn.primary', { type: 'submit', text: 'Play' })]);

      const ul = h('ul.list');
      window.STUDIES.forEach(function (st) {
        const li = h('li', {
          onclick: function () {
            Array.prototype.forEach.call(ul.children, function (c) { c.classList.remove('active'); });
            li.classList.add('active');
            start(st);
          }
        }, [h('span', { text: st.name }), h('small', { text: st.difficulty + ' · ' + st.goal })]);
        ul.appendChild(li);
      });

      ctx.root.appendChild(h('div', [
        ul,
        h('div.divider'),
        title, sub, setupEl,
        h('div.controls', [timerEl]),
        h('div', { style: { margin: '8px 0' } }, [movesEl]),
        form, feedback, ideaEl,
        h('div.controls', { style: { marginTop: '10px' } }, [
          h('button.btn', { text: 'Read position aloud', onclick: describePosition }),
          h('button.btn', { text: 'Idea', onclick: showIdea }),
          h('button.btn', { text: 'Give up', onclick: giveUp }),
          h('button.btn', { text: 'Restart', onclick: function () { if (spec) start(spec); } })
        ]),
        h('div.divider'),
        statsEl
      ]));

      function start(st) {
        spec = st;
        const parsed = PGN.parse('[FEN "' + st.fen + '"]\n[SetUp "1"]\n' + st.line);
        game = new Chess(st.fen);
        node = parsed.root;
        mySide = st.you;
        solved = false;
        failedMoves = 0;
        deadline = Date.now() + 20 * 60 * 1000;
        title.textContent = st.name;
        sub.textContent = (st.goal === 'draw' ? 'White to play and draw' :
          st.goal === 'mate' ? 'Mate is there — find it' : 'White to play and win') +
          (mySide === 'b' ? ' (you are Black)' : '');
        feedback.textContent = '';
        ideaEl.textContent = '';
        describePosition();
        board.setOrientation(mySide);
        board.setPosition(game, { animate: false });
        board.setMovable({
          color: mySide, dests: game.destinationsMap(),
          onMove: function (from, to) { play(from + to); }
        });
        board.opts.viewOnly = false;
        renderMoves();
        render();
        clearInterval(tick);
        tick = setInterval(updateClock, 500);
        updateClock();
        input.focus();
      }

      function describePosition() {
        if (!game) return;
        const map = game.piecesMap();
        const lists = { w: [], b: [] };
        Object.keys(map).sort().forEach(function (sq) {
          const p = map[sq];
          lists[p.color].push(Chess.PIECE_NAMES[p.type] + ' ' + sq);
        });
        setupEl.textContent = 'White: ' + lists.w.join(', ') + '  ·  Black: ' + lists.b.join(', ');
      }

      function updateClock() {
        if (!deadline) return;
        const left = deadline - Date.now();
        timerEl.textContent = left > 0 ? App.util.fmtTime(left) : '0:00';
        timerEl.classList.toggle('low', left < 60000);
        if (left <= 0) {
          clearInterval(tick);
          tick = null;
          feedback.className = 'feedback err';
          feedback.textContent = 'Time is up — try it again, or give up to see the solution.';
        }
      }

      function childrenOf(n) { return (n && n.children) || []; }

      function play(text) {
        if (!game || solved) return;
        if (game.turnColor() !== mySide) return;
        const value = String(text).trim();
        if (!value) return;
        const found = game.findMove(value);
        if (!found) {
          feedback.className = 'feedback err';
          feedback.textContent = '"' + value + '" is not legal here.';
          return;
        }
        const san = game.moveToSan(found, game.generateMoves());
        const match = childrenOf(node).find(function (c) { return c.san === san; });
        if (!match) {
          failedMoves++;
          App.stat(statKey, { wrong: 1 });
          feedback.className = 'feedback err';
          feedback.textContent = '✗ ' + san + ' is not the study move. Think again.';
          return;
        }
        apply(match);
        feedback.className = 'feedback ok';
        feedback.textContent = '✓ ' + san;
        if (game.isCheckmate()) { finish(true); return; }
        const replies = childrenOf(node);
        if (!replies.length) { finish(true); return; }
        setTimeout(function () {
          const pick = replies[Math.floor(Math.random() * replies.length)];
          apply(pick);
          feedback.className = 'feedback info';
          feedback.textContent = 'Reply: ' + pick.san;
          if (!childrenOf(node).length || game.isGameOver()) finish(true);
        }, 420);
      }

      function apply(child) {
        const done = game.move(child.san);
        node = child;
        board.setPosition(game, { animate: true, lastMove: done ? [done.from, done.to] : null });
        board.setMovable({
          color: mySide, dests: game.destinationsMap(),
          onMove: function (from, to) { play(from + to); }
        });
        renderMoves();
      }

      function finish(ok) {
        solved = ok;
        clearInterval(tick);
        tick = null;
        board.opts.viewOnly = true;
        board.setMovable({ color: null, dests: null, onMove: null });
        feedback.className = 'feedback ok';
        feedback.textContent = 'Solved — ' + (failedMoves ? failedMoves + ' wrong tries along the way.' : 'no wrong turns.');
        ideaEl.textContent = spec.idea;
        App.stat(statKey, { solved: 1, clean: failedMoves === 0 ? 1 : 0 });
        App.stat('l6-' + spec.id, { solved: 1 });
        render();
      }

      function showIdea() {
        if (!spec) return;
        ideaEl.textContent = spec.idea;
        App.stat(statKey, { hints: 1 });
      }

      function giveUp() {
        if (!spec) return;
        clearInterval(tick);
        tick = null;
        feedback.className = 'feedback info';
        feedback.textContent = 'Solution: ' + spec.line;
        ideaEl.textContent = spec.idea;
        App.stat(statKey, { gaveUp: 1 });
        if (board.opts.blindfold !== 'off') App.peek.flash(4);   // show what you were solving
        render();
      }

      function renderMoves() {
        movesEl.innerHTML = '';
        const sans = game ? game.historySan() : [];
        PGN.rows(sans).forEach(function (row, i) {
          movesEl.appendChild(h('span.num', { text: row.num + '.' }));
          movesEl.appendChild(h('span.mv', { text: row.white, class: (i * 2 === sans.length - 1) ? 'current' : '' }));
          movesEl.appendChild(h('span.mv', { text: row.black, class: (i * 2 + 1 === sans.length - 1) ? 'current' : '' }));
        });
      }

      function render() {
        const s = App.stat(statKey);
        statsEl.innerHTML = '';
        statsEl.appendChild(h('span', { html: 'studies solved <b>' + (s.solved || 0) + '</b>' }));
        statsEl.appendChild(h('span', { html: 'first time right <b>' + (s.clean || 0) + '</b>' }));
        statsEl.appendChild(h('span', { html: 'wrong moves <b>' + (s.wrong || 0) + '</b>' }));
      }

      render();
      return function () { clearInterval(tick); board.opts.viewOnly = true; };
    }
  });
})();
