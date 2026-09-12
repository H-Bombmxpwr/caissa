/* Level 1 — square colors. */
(function () {
  'use strict';
  const h = App.h;

  App.register({
    id: 'colors',
    num: 1,
    short: 'Square colors',
    title: 'Identify the color of a square',
    defaultBlindfold: 'full',
    blurb: 'Picture the square on the board — do not count files and ranks arithmetically. ' +
      'Press <span class="kbd">L</span> for light or <span class="kbd">D</span> for dark ' +
      '(or click). <span class="kbd">Enter</span> moves on after a miss.',
    mount: function (ctx) {
      const board = ctx.board;
      const statKey = 'l1';
      const saved = App.stat(statKey);
      let square = null, asked = 0, right = 0, streak = 0, best = saved.best || 0;
      let askedAt = 0, sessionMs = 0, sprintEnd = 0, sprintTimer = null, locked = false;

      const prompt = h('div.prompt');
      const sub = h('div.sub-prompt', { text: 'light or dark?' });
      const feedback = h('div.feedback');
      const statsEl = h('div.stats');
      const timerEl = h('div.timer');

      const lightBtn = h('button.lightbtn', { onclick: function () { answer('light'); } }, [
        h('span.key', { text: 'L' }), 'Light'
      ]);
      const darkBtn = h('button.darkbtn', { onclick: function () { answer('dark'); } }, [
        h('span.key', { text: 'D' }), 'Dark'
      ]);

      const fileSel = h('select', [
        h('option', { value: 'all', text: 'Whole board' }),
        h('option', { value: 'queenside', text: 'a–d files' }),
        h('option', { value: 'kingside', text: 'e–h files' }),
        h('option', { value: 'center', text: 'Central 16' })
      ]);

      const sprintBtn = h('button.btn', { text: '60s sprint', onclick: startSprint });
      const resetBtn = h('button.btn', {
        text: 'Reset record', onclick: function () { App.resetStat(statKey); best = 0; render(); }
      });

      ctx.root.appendChild(h('div', [
        prompt, sub,
        h('div.answer-grid', [lightBtn, darkBtn]),
        feedback,
        h('div.divider'),
        h('div.controls', [h('label.field', ['Range', fileSel]), sprintBtn, timerEl]),
        h('div.divider'),
        statsEl,
        h('div.controls', { style: { marginTop: '10px' } }, [resetBtn])
      ]));

      function pool() {
        const mode = fileSel.value;
        return function (sq) {
          const f = Chess.fileOf(sq), r = Chess.rankOf(sq);
          if (mode === 'queenside') return f <= 3;
          if (mode === 'kingside') return f >= 4;
          if (mode === 'center') return f >= 2 && f <= 5 && r >= 2 && r <= 5;
          return true;
        };
      }

      function next() {
        let sq;
        do { sq = App.util.randomSquare(pool()); } while (sq === square);
        square = sq;
        locked = false;
        askedAt = Date.now();
        prompt.textContent = square;
        board.setHighlights({});
        board.setShapes([]);
        render();
      }

      function answer(guess) {
        if (!square || locked) return;
        const truth = Chess.squareColor(square);
        const ok = guess === truth;
        asked++;
        sessionMs += Date.now() - askedAt;
        const btn = (guess === 'light') ? lightBtn : darkBtn;
        btn.classList.add(ok ? 'flash-ok' : 'flash-err');
        setTimeout(function () { btn.classList.remove('flash-ok', 'flash-err'); }, 260);

        if (ok) {
          right++; streak++;
          if (streak > best) { best = streak; App.stat(statKey, { best: best }); }
          feedback.className = 'feedback ok';
          feedback.textContent = square + ' is ' + truth + ' ✓';
          App.stat(statKey, { asked: 1, right: 1 });
          next();
        } else {
          streak = 0;
          locked = true;
          feedback.className = 'feedback err';
          feedback.textContent = square + ' is ' + truth + ' — look at it, then press Enter.';
          App.stat(statKey, { asked: 1 });
          board.setHighlights(Object.fromEntries([[square, truth === 'light' ? 'hl-yellow' : 'hl-blue']]));
          board.setShapes([{ square: square, brand: 'red' }]);
          render();
        }
      }

      function startSprint() {
        sprintEnd = Date.now() + 60000;
        asked = 0; right = 0; streak = 0; sessionMs = 0;
        clearInterval(sprintTimer);
        sprintTimer = setInterval(function () {
          const left = sprintEnd - Date.now();
          timerEl.textContent = App.util.fmtTime(left);
          timerEl.classList.toggle('low', left < 10000);
          if (left <= 0) {
            clearInterval(sprintTimer);
            sprintTimer = null;
            timerEl.textContent = '';
            const record = App.stat(statKey).sprint || 0;
            if (right > record) App.stat(statKey, { sprint: right });
            App.toast('Sprint over: ' + right + ' correct' + (right > record ? ' — new record!' : ''), 3500);
            render();
          }
        }, 200);
        next();
      }

      function render() {
        const acc = asked ? Math.round((right / asked) * 100) : 0;
        const avg = asked ? (sessionMs / asked / 1000).toFixed(1) : '0.0';
        const all = App.stat(statKey);
        statsEl.innerHTML = '';
        statsEl.appendChild(h('span', { html: 'session <b>' + right + '/' + asked + '</b> (' + acc + '%)' }));
        statsEl.appendChild(h('span', { html: 'streak <b>' + streak + '</b>' }));
        statsEl.appendChild(h('span', { html: 'best streak <b>' + best + '</b>' }));
        statsEl.appendChild(h('span', { html: 'avg <b>' + avg + 's</b>' }));
        if (all.sprint) statsEl.appendChild(h('span', { html: 'sprint record <b>' + all.sprint + '</b>' }));
        if (all.asked) {
          statsEl.appendChild(h('span', {
            html: 'all time <b>' + (all.right || 0) + '/' + all.asked + '</b>'
          }));
        }
      }

      function onKey(e) {
        const tag = (e.target.tagName || '').toLowerCase();
        if (tag === 'input' || tag === 'textarea') return;
        const k = e.key.toLowerCase();
        if (locked && (k === 'enter' || k === ' ')) { if (k === 'enter') { next(); return; } }
        if (k === 'l') answer('light');
        else if (k === 'd') answer('dark');
        else if (k === 'enter' && locked) next();
      }
      document.addEventListener('keydown', onKey);

      board.setPosition(new Chess('8/8/8/8/8/8/8/8 w - - 0 1'), { animate: false });
      next();

      return function () {
        document.removeEventListener('keydown', onKey);
        clearInterval(sprintTimer);
      };
    }
  });
})();
