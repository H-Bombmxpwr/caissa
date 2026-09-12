/* Board renderer in the spirit of lichess' chessground:
 * absolutely positioned pieces moved with CSS transforms so every change
 * animates smoothly, plus click/drag input, shapes and blindfold modes. */
(function (global) {
  'use strict';

  const FILES = 'abcdefgh';
  const PIECE_CLASS = { p: 'pawn', n: 'knight', b: 'bishop', r: 'rook', q: 'queen', k: 'king' };
  const COLOR_CLASS = { w: 'white', b: 'black' };

  let pieceUid = 0;

  /* Piece art lives next to this script (../assets/piece/<set>/), not next to the page,
     so work the base out from board.js' own URL instead of using a page-relative path. */
  const SCRIPT_SRC = (document.currentScript && document.currentScript.src) || '';
  const BASE = SCRIPT_SRC ? SCRIPT_SRC.replace(/\/js\/board\.js.*$/, '/') : '';
  let PIECE_SET = 'cburnett';
  function pieceArt(set, color, type) {
    return BASE + 'assets/piece/' + set + '/' + color + type.toUpperCase() + '.svg';
  }
  function pieceUrl(piece) {
    return pieceArt(PIECE_SET, piece.color, piece.type);
  }

  function el(tag, className) {
    const e = document.createElement(tag);
    if (className) e.className = className;
    return e;
  }

  function keyToCoords(key, orientation) {
    let file = FILES.indexOf(key[0]);
    let rank = parseInt(key[1], 10) - 1;
    if (orientation === 'w') return [file, 7 - rank];
    return [7 - file, rank];
  }

  function coordsToKey(x, y, orientation) {
    if (x < 0 || x > 7 || y < 0 || y > 7) return null;
    if (orientation === 'w') return FILES[x] + (8 - y);
    return FILES[7 - x] + (y + 1);
  }

  function distance(a, b) {
    const df = FILES.indexOf(a[0]) - FILES.indexOf(b[0]);
    const dr = parseInt(a[1], 10) - parseInt(b[1], 10);
    return Math.max(Math.abs(df), Math.abs(dr));
  }

  function Board(container, options) {
    this.opts = Object.assign({
      orientation: 'w',
      coordinates: true,
      blindfold: 'off',        // 'off' | 'pieces' | 'full'
      animationMs: 200,
      draggable: true,
      viewOnly: false
    }, options || {});

    this.container = container;
    this.pieces = {};          // key -> { type, color, el }
    this.movable = { color: null, dests: null, onMove: null, free: false };
    this.selected = null;
    this.lastMove = null;
    this.checkSquare = null;
    this.customHighlights = {};
    this.answerHighlights = {};   // computed hints — never shown during a peek
    this.shapes = [];
    this.answerShapes = [];
    this.drag = null;
    this.peeking = false;

    this._build();
  }

  Board.prototype._build = function () {
    const wrap = el('div', 'cg-wrap');
    wrap.style.setProperty('--anim', this.opts.animationMs + 'ms');
    const board = el('div', 'cg-board');
    this.squareEls = {};
    for (let y = 0; y < 8; y++) {
      for (let x = 0; x < 8; x++) {
        const sq = el('square');
        sq.style.transform = 'translate(' + (x * 100) + '%,' + (y * 100) + '%)';
        board.appendChild(sq);
        this.squareEls[x + ',' + y] = sq;
      }
    }
    this.boardEl = board;
    this.piecesEl = el('div', 'cg-pieces');
    this.svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    this.svg.setAttribute('class', 'cg-shapes');
    this.svg.setAttribute('viewBox', '0 0 8 8');
    this.coordsEl = el('div', 'cg-coords');

    wrap.appendChild(board);
    wrap.appendChild(this.svg);
    wrap.appendChild(this.piecesEl);
    wrap.appendChild(this.coordsEl);
    this.wrap = wrap;
    this.container.innerHTML = '';
    this.container.appendChild(wrap);

    this._renderCoords();
    this._renderSquares();
    this.setBlindfold(this.opts.blindfold);
    this._bindInput();
  };

  Board.prototype._renderCoords = function () {
    this.coordsEl.innerHTML = '';
    if (!this.opts.coordinates) return;
    const o = this.opts.orientation;
    for (let x = 0; x < 8; x++) {
      const f = el('coord', 'file');
      f.textContent = o === 'w' ? FILES[x] : FILES[7 - x];
      f.style.transform = 'translate(' + (x * 100) + '%, 700%)';
      f.classList.add((x % 2 === 0) ? 'light' : 'dark');
      this.coordsEl.appendChild(f);
    }
    for (let y = 0; y < 8; y++) {
      const r = el('coord', 'rank');
      r.textContent = o === 'w' ? (8 - y) : (y + 1);
      r.style.transform = 'translate(0, ' + (y * 100) + '%)';
      r.classList.add((y % 2 === 0) ? 'dark' : 'light');
      this.coordsEl.appendChild(r);
    }
  };

  Board.prototype._renderSquares = function () {
    const o = this.opts.orientation;
    for (let y = 0; y < 8; y++) {
      for (let x = 0; x < 8; x++) {
        const sq = this.squareEls[x + ',' + y];
        const key = coordsToKey(x, y, o);
        sq.dataset.key = key;
        const light = (FILES.indexOf(key[0]) + parseInt(key[1], 10)) % 2 === 0;
        sq.className = light ? 'light' : 'dark';
        if (this.lastMove && (this.lastMove[0] === key || this.lastMove[1] === key)) sq.classList.add('last-move');
        if (this.selected === key) sq.classList.add('selected');
        if (this.checkSquare === key) sq.classList.add('check');
        const custom = this.customHighlights[key];
        if (custom) sq.classList.add(custom);
        /* a peek should show the position, not the answer worked out for you */
        if (!this.peeking) {
          const answer = this.answerHighlights[key];
          if (answer) sq.classList.add(answer);
        }
        if (this.selected && this._destsFrom(this.selected).indexOf(key) > -1) {
          sq.classList.add(this.pieces[key] ? 'dest-occupied' : 'dest');
        }
      }
    }
  };

  Board.prototype._destsFrom = function (key) {
    if (this.movable.free) {
      return Chess.SQUARES.filter(function (s) { return s !== key; });
    }
    if (!this.movable.dests) return [];
    return this.movable.dests[key] || [];
  };

  /* ---------- pieces & animation ---------- */

  Board.prototype._place = function (pieceEl, key, animate) {
    const [x, y] = keyToCoords(key, this.opts.orientation);
    if (!animate) pieceEl.classList.add('no-anim');
    pieceEl.style.transform = 'translate(' + (x * 100) + '%,' + (y * 100) + '%)';
    if (!animate) {
      void pieceEl.offsetWidth;               // flush, then re-enable transitions
      pieceEl.classList.remove('no-anim');
    }
  };

  Board.prototype._newPiece = function (piece, key, fade) {
    const p = el('piece', COLOR_CLASS[piece.color] + ' ' + PIECE_CLASS[piece.type]);
    p.dataset.uid = ++pieceUid;
    p.style.backgroundImage = 'url("' + pieceUrl(piece) + '")';
    this._place(p, key, false);
    if (fade) {
      p.classList.add('fade-in');
      requestAnimationFrame(function () { p.classList.remove('fade-in'); });
    }
    this.piecesEl.appendChild(p);
    return p;
  };

  /* Diff current position against the new one and reuse elements so pieces
   * glide to their new square instead of blinking. */
  Board.prototype.setPieces = function (map, opts) {
    opts = opts || {};
    const animate = opts.animate !== false;
    const current = this.pieces;
    const next = {};
    const leftovers = [];   // pieces whose square is no longer theirs

    Object.keys(current).forEach(function (key) {
      const p = current[key];
      const target = map[key];
      if (target && target.type === p.type && target.color === p.color) {
        next[key] = p;
      } else {
        leftovers.push({ key: key, piece: p });
      }
    });

    const additions = Object.keys(map).filter(function (k) { return !next[k]; });

    additions.forEach((key) => {
      const want = map[key];
      let bestIndex = -1, bestDist = Infinity;
      for (let i = 0; i < leftovers.length; i++) {
        const cand = leftovers[i];
        if (!cand || cand.used) continue;
        if (cand.piece.type !== want.type || cand.piece.color !== want.color) continue;
        const d = distance(cand.key, key);
        if (d < bestDist) { bestDist = d; bestIndex = i; }
      }
      if (bestIndex > -1) {
        const cand = leftovers[bestIndex];
        cand.used = true;
        this._place(cand.piece.el, key, animate);
        next[key] = { type: want.type, color: want.color, el: cand.piece.el };
      } else {
        next[key] = { type: want.type, color: want.color, el: this._newPiece(want, key, animate) };
      }
    });

    leftovers.forEach((cand) => {
      if (cand.used) return;
      const node = cand.piece.el;
      if (animate) {
        node.classList.add('fade-out');
        setTimeout(function () { if (node.parentNode) node.parentNode.removeChild(node); }, this.opts.animationMs);
      } else if (node.parentNode) {
        node.parentNode.removeChild(node);
      }
    });

    this.pieces = next;
    if (opts.lastMove !== undefined) this.lastMove = opts.lastMove;
    if (opts.check !== undefined) this.checkSquare = opts.check;
    this.selected = null;
    this._renderSquares();
  };

  Board.prototype.setPosition = function (fenOrGame, opts) {
    const game = (typeof fenOrGame === 'string') ? new Chess(fenOrGame) : fenOrGame;
    const o = opts || {};
    if (o.check === undefined) {
      o.check = game.inCheck && game.inCheck() ? findKing(game, game.turnColor()) : null;
    }
    this.setPieces(game.piecesMap(), o);
  };

  function findKing(game, color) {
    const map = game.piecesMap();
    return Object.keys(map).find(function (k) { return map[k].type === 'k' && map[k].color === color; }) || null;
  }

  Board.prototype.clear = function (animate) { this.setPieces({}, { animate: animate !== false }); };

  /* ---------- decoration ---------- */

  Board.prototype.setLastMove = function (lm) { this.lastMove = lm; this._renderSquares(); };
  Board.prototype.setCheck = function (sq) { this.checkSquare = sq; this._renderSquares(); };
  /* opts.answer marks decoration that gives the exercise away, so it is suppressed
     while the board is being peeked at */
  /* Same square pair twice removes it; a different colour recolours it in place. */
  Board.prototype._addShape = function (from, to, brand) {
    const same = s => (s.square ? s.square === from && from === to : s.from === from && s.to === to);
    const existing = this.shapes.find(same);
    if (existing) this.shapes = this.shapes.filter(s => !same(s));
    if (!existing || existing.brand !== brand) {
      this.shapes.push(from === to ? { square: from, brand: brand } : { from: from, to: to, brand: brand });
    }
    this._renderShapes();
    this._shapesChanged();
  };

  /* Only the user's own edits report back; setShapes() is the app talking to the board. */
  Board.prototype._shapesChanged = function () {
    if (this.opts.onShapes) this.opts.onShapes(this.shapes.slice());
  };

  Board.prototype.setHighlights = function (map, opts) {
    if (opts && opts.answer) this.answerHighlights = map || {};
    else this.customHighlights = map || {};
    this._renderSquares();
  };
  Board.prototype.addHighlight = function (key, cls) { this.customHighlights[key] = cls; this._renderSquares(); };

  Board.prototype.setOrientation = function (color) {
    this.opts.orientation = color;
    this._renderCoords();
    this._renderSquares();
    const self = this;
    Object.keys(this.pieces).forEach(function (key) { self._place(self.pieces[key].el, key, false); });
    this._renderShapes();
  };
  Board.prototype.toggleOrientation = function () {
    this.setOrientation(this.opts.orientation === 'w' ? 'b' : 'w');
  };

  /* shapes: [{from,to,brand,label}] arrows or [{square,brand,label}] circles.
     label is a short badge drawn in the destination square's corner. */
  Board.prototype.setShapes = function (shapes, opts) {
    if (opts && opts.answer) this.answerShapes = shapes || [];
    else this.shapes = shapes || [];
    this._renderShapes();
  };

  Board.prototype._renderShapes = function () {
    const o = this.opts.orientation;
    function badge(label, x, y, brand) {
      if (label === undefined || label === null || label === '') return '';
      const text = String(label).replace(/[&<>]/g, '');
      return '<circle cx="' + (x + 0.19) + '" cy="' + (y + 0.19) + '" r="0.17" stroke-width="0" class="shape-' + brand + '"/>' +
        '<text x="' + (x + 0.19) + '" y="' + (y + 0.19) + '" class="shape-label">' + text + '</text>';
    }
    let out = '<defs>';
    ['green', 'blue', 'red', 'yellow', 'purple'].forEach(function (c) {
      out += '<marker id="arrow-' + c + '" orient="auto" markerWidth="4" markerHeight="8" refX="2.05" refY="2.01">' +
        '<path d="M0,0 V4 L3,2 Z" class="shape-' + c + '"/></marker>';
    });
    out += '</defs>';
    let visible = this.peeking ? this.shapes : this.shapes.concat(this.answerShapes);
    if (this.drawing) visible = visible.concat([this.drawing.from === this.drawing.to
      ? { square: this.drawing.from, brand: this.drawing.brand }
      : { from: this.drawing.from, to: this.drawing.to, brand: this.drawing.brand }]);
    visible.forEach(function (s) {
      const brand = s.brand || 'green';
      if (s.square) {
        const [x, y] = keyToCoords(s.square, o);
        out += '<circle cx="' + (x + 0.5) + '" cy="' + (y + 0.5) + '" r="0.44" class="shape-' + brand +
          '" fill="none" stroke-width="0.07"/>' + badge(s.label, x, y, brand);
      } else if (s.from && s.to) {
        const [x1, y1] = keyToCoords(s.from, o);
        const [x2, y2] = keyToCoords(s.to, o);
        const ax = x1 + 0.5, ay = y1 + 0.5;
        let bx = x2 + 0.5, by = y2 + 0.5;
        const dx = bx - ax, dy = by - ay, len = Math.sqrt(dx * dx + dy * dy) || 1;
        bx -= (dx / len) * 0.3; by -= (dy / len) * 0.3;
        out += '<line x1="' + ax + '" y1="' + ay + '" x2="' + bx + '" y2="' + by +
          '" class="shape-' + brand + '" stroke-width="0.12" marker-end="url(#arrow-' + brand + ')"/>';
        out += badge(s.label, x2, y2, brand);
      }
    });
    this.svg.innerHTML = out;
  };

  /* ---------- blindfold & peeking ---------- */

  Board.prototype.setBlindfold = function (mode) {
    this.opts.blindfold = mode;
    this.wrap.classList.toggle('bf-pieces', mode === 'pieces' && !this.peeking);
    this.wrap.classList.toggle('bf-full', mode === 'full' && !this.peeking);
  };

  Board.prototype.setPeeking = function (on) {
    this.peeking = !!on;
    this.wrap.classList.toggle('peeking', this.peeking);
    this.setBlindfold(this.opts.blindfold);
    this._renderSquares();     // drop answer highlights while revealed
    this._renderShapes();
  };

  Board.prototype.isHidden = function () {
    return this.opts.blindfold !== 'off' && !this.peeking;
  };

  /* ---------- input ---------- */

  Board.prototype.setMovable = function (cfg) {
    this.movable = Object.assign({ color: null, dests: null, onMove: null, free: false }, cfg || {});
    this.selected = null;
    this._renderSquares();
  };

  Board.prototype._keyAt = function (evt) {
    const rect = this.wrap.getBoundingClientRect();
    const x = Math.floor(((evt.clientX - rect.left) / rect.width) * 8);
    const y = Math.floor(((evt.clientY - rect.top) / rect.height) * 8);
    return coordsToKey(x, y, this.opts.orientation);
  };

  Board.prototype._canMoveFrom = function (key) {
    const piece = this.pieces[key];
    if (this.opts.viewOnly) return false;
    if (this.movable.free) return !!piece;
    if (!piece) return false;
    if (this.movable.color && this.movable.color !== 'both' && piece.color !== this.movable.color) return false;
    return this._destsFrom(key).length > 0;
  };

  Board.prototype._bindInput = function () {
    const self = this;
    // Arrow drawing follows chessground, the library lichess itself draws with: a
    // right-drag (or shift-drag) paints a live preview that follows the pointer,
    // releasing commits it, drawing the same arrow again removes it, and drawing it in
    // another colour recolours it in place rather than stacking a second arrow on top.
    function eventBrand(e) {
      const modA = (e.shiftKey || e.ctrlKey) && e.button === 2;
      const modB = e.altKey || e.metaKey;
      return ['green', 'red', 'blue', 'yellow'][(modA ? 1 : 0) + (modB ? 2 : 0)];
    }
    this.wrap.addEventListener('contextmenu', e => e.preventDefault());
    this.wrap.addEventListener('pointerdown', function (e) {
      /* drawing is about the position, not the moves, so it works on view-only boards */
      if (e.button !== 2 && !(e.button === 0 && e.shiftKey)) return;
      const from = self._keyAt(e);
      if (!from) return;
      e.preventDefault();
      self.drawing = { from: from, to: from, brand: eventBrand(e) };
      self.wrap.setPointerCapture(e.pointerId);
      self._renderShapes();
    });
    this.wrap.addEventListener('pointermove', function (e) {
      if (!self.drawing || self.drawPending) return;
      self.drawPending = true;                       // one redraw a frame, as chessground does
      requestAnimationFrame(function () {
        self.drawPending = false;
        if (!self.drawing) return;
        const to = self._keyAt(e) || self.drawing.from;
        if (to === self.drawing.to) return;
        self.drawing.to = to;
        self._renderShapes();
      });
    });
    this.wrap.addEventListener('pointerup', function (e) {
      if (!self.drawing) return;
      const current = self.drawing;
      self.drawing = null;
      const to = self._keyAt(e);
      if (to) self._addShape(current.from, to, current.brand);
      else self._renderShapes();                     // released off the board: nothing drawn
    });
    this.wrap.addEventListener('pointercancel', function () { self.drawing = null; self._renderShapes(); });

    this.wrap.addEventListener('pointerdown', function (e) {
      if (self.opts.viewOnly) return;
      if (e.button !== 0 || e.shiftKey) return;
      const key = self._keyAt(e);
      if (!key) return;
      e.preventDefault();
      if (!self.selected && self.shapes.length) { self.shapes = []; self._renderShapes(); self._shapesChanged(); }

      if (self.selected && self.selected !== key && self._destsFrom(self.selected).indexOf(key) > -1) {
        self._tryMove(self.selected, key);
        return;
      }
      if (!self._canMoveFrom(key)) {
        self.selected = null;
        self._renderSquares();
        return;
      }
      self.selected = key;
      self._renderSquares();

      if (!self.opts.draggable) return;
      const pieceEl = self.pieces[key] && self.pieces[key].el;
      if (!pieceEl) return;
      const rect = self.wrap.getBoundingClientRect();
      self.drag = { from: key, el: pieceEl, rect: rect, moved: false };
      pieceEl.classList.add('dragging');
      self._dragTo(e);
      self.wrap.setPointerCapture(e.pointerId);
    });

    this.wrap.addEventListener('pointermove', function (e) {
      if (!self.drag) return;
      self.drag.moved = true;
      self._dragTo(e);
    });

    const release = function (e) {
      if (!self.drag) return;
      const drag = self.drag;
      self.drag = null;
      drag.el.classList.remove('dragging');
      drag.el.style.left = '';
      drag.el.style.top = '';
      // Leave a legal drop at its released location; setPosition animates to the square.
      const key = self._keyAt(e);
      if (e.type !== 'pointercancel' && drag.moved && key && key !== drag.from) {
        drag.el.classList.remove('no-anim');
        if (self._destsFrom(drag.from).indexOf(key) > -1) {
          self._tryMove(drag.from, key);
          // Promotion can open a dialog without committing a position yet.
          if(self.pieces[drag.from]?.el===drag.el)self._place(drag.el,drag.from,true);
        }
        else { self._place(drag.el, drag.from, true);self.selected = null; self._renderSquares(); }
      } else self._place(drag.el, drag.from, false);
    };
    this.wrap.addEventListener('pointerup', release);
    this.wrap.addEventListener('pointercancel', release);
  };

  Board.prototype._dragTo = function (e) {
    const d = this.drag;
    const size = d.rect.width / 8;
    d.el.classList.add('no-anim');
    d.el.style.transform = 'translate(' + (e.clientX - d.rect.left - size / 2) + 'px,' +
      (e.clientY - d.rect.top - size / 2) + 'px)';
  };

  Board.prototype._tryMove = function (from, to) {
    this.selected = null;
    const cb = this.movable.onMove;
    this._renderSquares();
    if (cb) cb(from, to);
  };

  Board.prototype.selectSquare = function (key) { this.selected = key; this._renderSquares(); };

  global.Board = Board;
  // The bundled sets, in the order the settings picker offers them.
  Board.PIECE_SETS = [['cburnett','Cburnett'],['merida','Merida'],['alpha','Alpha'],['maestro','Maestro'],
    ['chessnut','Chessnut'],['fantasy','Fantasy'],['celtic','Celtic'],['spatial','Spatial'],['rhosgfx','Rhos']];
  Board.pieceArt = pieceArt;
  Board.setPieceSet = function(name){PIECE_SET=Board.PIECE_SETS.some(s=>s[0]===name)?name:'cburnett';};
  Board.prototype.refreshPieceArt = function(){Object.values(this.pieces).forEach(p=>p.el.style.backgroundImage='url("'+pieceUrl(p)+'")');};
})(window);
