/* Level 2 — piece tours: route a knight/bishop/rook from A to B, blindfolded. */
(function () {
  'use strict';
  const h = App.h;

  App.register({
    id: 'tours',
    num: 2,
    short: 'Piece tours',
    title: 'Basic piece tours',
    defaultBlindfold: 'full',
    blurb: 'Map a route from the start square to the target. Type the squares you land on, ' +
      'e.g. <code>c5 f8</code> (the start square is optional). Shortest route wins style points.',
    mount: function (ctx) {
      const board = ctx.board;
      const statKey = 'l2';
      let piece = 'n', from = null, to = null, best = null, solved = false;

      const pieceSel = h('select', { onchange: function () { piece = this.value; next(); } }, [
        h('option', { value: 'n', text: 'Knight' }),
        h('option', { value: 'b', text: 'Bishop' }),
        h('option', { value: 'r', text: 'Rook' })
      ]);
      const lenSel = h('select', { onchange: next }, [
        h('option', { value: '0', text: 'Any length' }),
        h('option', { value: '2', text: 'Exactly 2 moves' }),
        h('option', { value: '3', text: 'Exactly 3 moves' }),
        h('option', { value: '4', text: '4+ moves' })
      ]);

      const prompt = h('div.prompt.small');
      const sub = h('div.sub-prompt');
      const input = h('input', { type: 'text', placeholder: 'e.g. c5 f8', autocomplete: 'off', spellcheck: 'false' });
      const feedback = h('div.feedback');
      const statsEl = h('div.stats');

      const form = h('form.move-input', {
        onsubmit: function (e) { e.preventDefault(); check(input.value); }
      }, [input, h('button.btn.primary', { type: 'submit', text: 'Check' })]);

      ctx.root.appendChild(h('div', [
        prompt, sub, form, feedback,
        h('div.divider'),
        h('div.controls', [
          h('label.field', ['Piece', pieceSel]),
          h('label.field', ['Route', lenSel]),
          h('button.btn', { text: 'Show solution', onclick: reveal }),
          h('button.btn', { text: 'New (n)', onclick: next })
        ]),
        h('div.divider'),
        statsEl
      ]));

      function pieceName() { return { n: 'Knight', b: 'Bishop', r: 'Rook' }[piece]; }

      function next() {
        solved = false;
        feedback.textContent = '';
        input.value = '';
        const want = parseInt(lenSel.value, 10);
        let guard = 0;
        do {
          from = App.util.randomSquare();
          to = App.util.randomSquare();
          if (piece === 'b' && Chess.squareColor(from) !== Chess.squareColor(to)) { to = null; continue; }
          best = (from && to) ? App.util.shortestPath(piece, from, to) : null;
        } while ((++guard < 500) && (!best || best.length < 3 ||
          (want === 2 && best.length !== 3) ||
          (want === 3 && best.length !== 4) ||
          (want === 4 && best.length < 5)));

        prompt.textContent = pieceName() + ':  ' + from + '  →  ' + to;
        sub.textContent = 'shortest route: ' + (best.length - 1) + ' move' + (best.length === 2 ? '' : 's');
        board.setHighlights({}, { answer: true });
        board.setShapes([], { answer: true });
        board.setPieces({}, { animate: false });
        input.focus();
        render();
      }

      function showPieces() {
        const map = {};
        map[from] = { type: piece, color: 'w' };
        map[to] = { type: 'k', color: 'b' };
        board.setPieces(map, { animate: false });
        board.setHighlights({ [from]: 'hl-blue', [to]: 'hl-green' }, { answer: true });
      }

      function parseRoute(text) {
        const squares = (String(text).toLowerCase().match(/[a-h][1-8]/g) || []);
        if (!squares.length) return null;
        if (squares[0] !== from) squares.unshift(from);
        return squares;
      }

      function legalHop(a, b) {
        const moves = { n: App.util.knightMoves, b: App.util.bishopMoves, r: App.util.rookMoves }[piece](a);
        return moves.indexOf(b) > -1;
      }

      function check(text) {
        const route = parseRoute(text);
        if (!route) { feedback.className = 'feedback err'; feedback.textContent = 'Type squares like "c5 f8".'; return; }
        for (let i = 1; i < route.length; i++) {
          if (!legalHop(route[i - 1], route[i])) {
            feedback.className = 'feedback err';
            feedback.textContent = '✗ ' + route[i - 1] + '–' + route[i] + ' is not a ' + pieceName().toLowerCase() + ' move.';
            App.stat(statKey, { asked: 1 });
            return;
          }
        }
        if (route[route.length - 1] !== to) {
          feedback.className = 'feedback err';
          feedback.textContent = '✗ legal moves, but you finished on ' + route[route.length - 1] + ', not ' + to + '.';
          App.stat(statKey, { asked: 1 });
          return;
        }
        const used = route.length - 1, optimal = best.length - 1;
        solved = true;
        drawRoute(route, used === optimal ? 'green' : 'blue');
        if (used === optimal) {
          feedback.className = 'feedback ok';
          feedback.textContent = '✓ ' + route.join('–') + ' — optimal in ' + used + '.';
          App.stat(statKey, { asked: 1, right: 1, optimal: 1 });
        } else {
          feedback.className = 'feedback info';
          feedback.textContent = '✓ valid in ' + used + ' moves, but ' + optimal + ' is possible: ' + best.join('–');
          App.stat(statKey, { asked: 1, right: 1 });
        }
        render();
      }

      function drawRoute(route, brand) {
        const shapes = [];
        for (let i = 1; i < route.length; i++) shapes.push({ from: route[i - 1], to: route[i], brand: brand });
        showPieces();
        board.setShapes(shapes, { answer: true });
      }

      function reveal() {
        drawRoute(best, 'yellow');
        feedback.className = 'feedback info';
        feedback.textContent = 'Solution: ' + best.join('–');
        if (!solved) App.stat(statKey, { asked: 1, shown: 1 });
      }

      function render() {
        const s = App.stat(statKey);
        statsEl.innerHTML = '';
        statsEl.appendChild(h('span', { html: 'solved <b>' + (s.right || 0) + '/' + (s.asked || 0) + '</b>' }));
        statsEl.appendChild(h('span', { html: 'optimal <b>' + (s.optimal || 0) + '</b>' }));
        if (s.shown) statsEl.appendChild(h('span', { html: 'given up <b>' + s.shown + '</b>' }));
      }

      function onKey(e) {
        if (e.key === 'n' && e.target !== input && !e.ctrlKey && !e.metaKey) { e.preventDefault(); next(); }
      }
      document.addEventListener('keydown', onKey);

      next();
      return function () { document.removeEventListener('keydown', onKey); };
    }
  });
})();
