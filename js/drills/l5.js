/* Level 5 — knight's tour past an enemy queen. */
(function () {
  'use strict';
  const h = App.h;

  App.register({
    id: 'knight-tour',
    num: 5,
    short: 'Knight vs Queen',
    title: "Complete the knight's tour vs a queen",
    defaultBlindfold: 'full',
    blurb: 'Visit every square the queen does not attack, never landing on one she does. ' +
      'Type the squares one at a time (<code>f2 d3 …</code>) — several at once is fine too.',
    mount: function (ctx) {
      const board = ctx.board;
      const statKey = 'l5';

      let knightStart = 'h1', queenSquare = 'd4';
      let visited = [], attacked = {}, targets = [], done = false, startedAt = 0;

      const prompt = h('div.prompt.small');
      const sub = h('div.sub-prompt');
      const bar = h('div.progress', [h('div', { style: { width: '0%' } })]);
      const feedback = h('div.feedback');
      const trail = h('div.hint.mono', { style: { wordBreak: 'break-word', margin: '8px 0' } });
      const statsEl = h('div.stats');
      const timerEl = h('div.timer');

      const input = h('input', { type: 'text', placeholder: 'next square', autocomplete: 'off', spellcheck: 'false' });
      const form = h('form.move-input', {
        onsubmit: function (e) { e.preventDefault(); submit(input.value); input.value = ''; }
      }, [input, h('button.btn.primary', { type: 'submit', text: 'Hop' })]);

      const knightSel = h('input', { type: 'text', value: 'h1', size: '3', maxlength: '2' });
      const queenSel = h('input', { type: 'text', value: 'd4', size: '3', maxlength: '2' });

      ctx.root.appendChild(h('div', [
        prompt, sub, bar,
        h('div', { style: { marginTop: '10px' } }, [form]),
        feedback, trail,
        h('div.controls', [
          h('label.field', ['Knight', knightSel]),
          h('label.field', ['Queen', queenSel]),
          h('button.btn', { text: 'New tour', onclick: function () { setup(knightSel.value, queenSel.value); } }),
          h('button.btn', { text: 'Random', onclick: randomSetup }),
          h('button.btn', { text: 'Undo', onclick: undo }),
          timerEl
        ]),
        h('div.divider'),
        h('p.hint', { text: 'A square is "safe" if the queen does not attack it. The knight may pass ' +
          'through nothing — only the squares it lands on matter.' }),
        statsEl
      ]));

      /* squares the lone queen covers (plus the square she stands on) */
      function computeAttacked(q) {
        const probe = new Chess('8/8/8/8/8/8/8/8 w - - 0 1');
        probe.put({ type: 'q', color: 'b' }, q);
        const out = {};
        out[q] = true;
        Chess.SQUARES.forEach(function (sq) {
          if (sq !== q && probe.attacked('b', sqIndex(sq))) out[sq] = true;
        });
        return out;
      }

      function sqIndex(name) {
        return (8 - parseInt(name.charAt(1), 10)) * 16 + 'abcdefgh'.indexOf(name.charAt(0));
      }

      function setup(kStart, qSq) {
        kStart = String(kStart || '').toLowerCase().trim();
        qSq = String(qSq || '').toLowerCase().trim();
        if (!Chess.isSquare(kStart) || !Chess.isSquare(qSq)) {
          feedback.className = 'feedback err';
          feedback.textContent = 'Give two squares like h1 and d4.';
          return;
        }
        attacked = computeAttacked(qSq);
        if (attacked[kStart]) {
          feedback.className = 'feedback err';
          feedback.textContent = 'The knight cannot start on ' + kStart + ' — the queen attacks it.';
          return;
        }
        knightStart = kStart;
        queenSquare = qSq;
        visited = [knightStart];
        done = false;
        startedAt = Date.now();
        targets = Chess.SQUARES.filter(function (s) { return !attacked[s]; });
        feedback.className = 'feedback';
        feedback.textContent = '';
        knightSel.value = knightStart;
        queenSel.value = queenSquare;
        draw();
        input.focus();
      }

      function randomSetup() {
        let q, k, safe;
        do {
          q = App.util.randomSquare();
          const att = computeAttacked(q);
          safe = Chess.SQUARES.filter(function (s) { return !att[s]; });
          k = safe[Math.floor(Math.random() * safe.length)];
        } while (!k || safe.length < 20);
        setup(k, q);
      }

      function draw() {
        const map = {};
        map[queenSquare] = { type: 'q', color: 'b' };
        map[visited[visited.length - 1]] = { type: 'n', color: 'w' };
        board.setPieces(map, { animate: true });
        const hl = {};
        Object.keys(attacked).forEach(function (sq) { hl[sq] = 'hl-red'; });
        visited.forEach(function (sq) { hl[sq] = 'hl-green'; });
        hl[queenSquare] = 'hl-red';
        board.setHighlights(hl, { answer: true });

        const left = targets.length - visited.length;
        prompt.textContent = 'Knight on ' + visited[visited.length - 1] + ' · Queen on ' + queenSquare;
        sub.textContent = visited.length + ' of ' + targets.length + ' safe squares visited · ' + left + ' to go';
        bar.firstChild.style.width = Math.round((visited.length / targets.length) * 100) + '%';
        trail.textContent = visited.join(' → ');
        timerEl.textContent = startedAt ? App.util.fmtTime(Date.now() - startedAt) : '';
        render();
      }

      function submit(text) {
        if (done) return;
        const squares = String(text).toLowerCase().match(/[a-h][1-8]/g);
        if (!squares) {
          feedback.className = 'feedback err';
          feedback.textContent = 'Type a square such as f2.';
          return;
        }
        for (let i = 0; i < squares.length; i++) {
          if (!hop(squares[i])) break;
        }
        draw();
      }

      function hop(sq) {
        const from = visited[visited.length - 1];
        if (App.util.knightMoves(from).indexOf(sq) === -1) {
          feedback.className = 'feedback err';
          feedback.textContent = '✗ ' + from + '–' + sq + ' is not a knight move.';
          App.stat(statKey, { errors: 1 });
          return false;
        }
        if (attacked[sq]) {
          feedback.className = 'feedback err';
          feedback.textContent = '✗ the queen attacks ' + sq + '.';
          App.stat(statKey, { errors: 1, captured: 1 });
          return false;
        }
        if (visited.indexOf(sq) > -1) {
          feedback.className = 'feedback err';
          feedback.textContent = '✗ ' + sq + ' has already been visited.';
          App.stat(statKey, { errors: 1 });
          return false;
        }
        visited.push(sq);
        feedback.className = 'feedback ok';
        feedback.textContent = '✓ ' + sq;
        if (visited.length === targets.length) {
          done = true;
          const secs = Math.round((Date.now() - startedAt) / 1000);
          feedback.textContent = '✓ Tour complete — all ' + targets.length + ' safe squares in ' +
            App.util.fmtTime(Date.now() - startedAt) + '.';
          App.stat(statKey, { tours: 1 });
          const prev = App.stat(statKey).bestTime;
          if (!prev || secs < prev) App.stat(statKey, { bestTime: secs });
          App.toast('Tour complete!', 3000);
        }
        return true;
      }

      function undo() {
        if (visited.length > 1) { visited.pop(); done = false; draw(); }
      }

      function render() {
        const s = App.stat(statKey);
        statsEl.innerHTML = '';
        statsEl.appendChild(h('span', { html: 'tours finished <b>' + (s.tours || 0) + '</b>' }));
        statsEl.appendChild(h('span', { html: 'wrong hops <b>' + (s.errors || 0) + '</b>' }));
        if (s.bestTime) statsEl.appendChild(h('span', { html: 'best time <b>' + App.util.fmtTime(s.bestTime * 1000) + '</b>' }));
      }

      const tick = setInterval(function () {
        if (startedAt && !done) timerEl.textContent = App.util.fmtTime(Date.now() - startedAt);
      }, 1000);

      setup('h1', 'd4');
      return function () { clearInterval(tick); };
    }
  });
})();
