/* Blindfold Trainer - chess rules engine.
 * 0x88 board, ES5 syntax on purpose so it can be perft-tested with cscript.
 * Exposes global `Chess` (factory, `new` optional). */
(function (global) {
  'use strict';

  var WHITE = 'w', BLACK = 'b';
  var PAWN = 'p', KNIGHT = 'n', BISHOP = 'b', ROOK = 'r', QUEEN = 'q', KING = 'k';
  var DEFAULT_FEN = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';

  var BITS = {
    NORMAL: 1, CAPTURE: 2, BIG_PAWN: 4, EP_CAPTURE: 8,
    PROMOTION: 16, KSIDE_CASTLE: 32, QSIDE_CASTLE: 64
  };

  var PAWN_OFFSETS = { w: [-16, -32, -17, -15], b: [16, 32, 17, 15] };
  var PIECE_OFFSETS = {
    n: [-18, -33, -31, -14, 18, 33, 31, 14],
    b: [-17, -15, 17, 15],
    r: [-16, 1, 16, -1],
    q: [-17, -16, -15, 1, 17, 16, 15, -1],
    k: [-17, -16, -15, 1, 17, 16, 15, -1]
  };

  /* attack lookup, index = 119 + from - to */
  var A_PW = 1, A_PB = 2, A_N = 4, A_B = 8, A_R = 16, A_Q = 32, A_K = 64;
  var ATTACKS = new Array(240), RAYS = new Array(240);
  (function buildTables() {
    var i;
    for (i = 0; i < 240; i++) { ATTACKS[i] = 0; RAYS[i] = 0; }
    function idx(from, to) { return 119 + from - to; }
    for (var from = 0; from < 128; from++) {
      if (from & 0x88) continue;
      var d, to, j;
      for (d = 0; d < PIECE_OFFSETS.n.length; d++) {
        to = from + PIECE_OFFSETS.n[d];
        if (!(to & 0x88)) ATTACKS[idx(from, to)] |= A_N;
      }
      for (d = 0; d < PIECE_OFFSETS.k.length; d++) {
        to = from + PIECE_OFFSETS.k[d];
        if (!(to & 0x88)) ATTACKS[idx(from, to)] |= A_K;
      }
      var wp = [from - 17, from - 15], bp = [from + 17, from + 15];
      for (d = 0; d < 2; d++) {
        if (!(wp[d] & 0x88)) ATTACKS[idx(from, wp[d])] |= A_PW;
        if (!(bp[d] & 0x88)) ATTACKS[idx(from, bp[d])] |= A_PB;
      }
      for (d = 0; d < PIECE_OFFSETS.b.length; d++) {
        var off = PIECE_OFFSETS.b[d];
        for (j = from + off; !(j & 0x88); j += off) {
          ATTACKS[idx(from, j)] |= (A_B | A_Q);
          RAYS[idx(from, j)] = off;
        }
      }
      for (d = 0; d < PIECE_OFFSETS.r.length; d++) {
        var off2 = PIECE_OFFSETS.r[d];
        for (j = from + off2; !(j & 0x88); j += off2) {
          ATTACKS[idx(from, j)] |= (A_R | A_Q);
          RAYS[idx(from, j)] = off2;
        }
      }
    }
  })();

  var SQUARES = {};
  (function () {
    var files = 'abcdefgh';
    for (var s = 0; s < 128; s++) {
      if (s & 0x88) continue;
      SQUARES[files.charAt(s & 15) + (8 - (s >> 4))] = s;
    }
  })();

  function algebraic(sq) { return 'abcdefgh'.charAt(sq & 15) + (8 - (sq >> 4)); }
  function fileOf(sq) { return sq & 15; }
  function rankOf(sq) { return sq >> 4; }   /* 0 = rank 8, 7 = rank 1 */
  function swapColor(c) { return c === WHITE ? BLACK : WHITE; }
  function isDigit(c) { return '0123456789'.indexOf(c) !== -1; }

  var ROOKS = {
    w: [{ square: SQUARES.a1, flag: BITS.QSIDE_CASTLE }, { square: SQUARES.h1, flag: BITS.KSIDE_CASTLE }],
    b: [{ square: SQUARES.a8, flag: BITS.QSIDE_CASTLE }, { square: SQUARES.h8, flag: BITS.KSIDE_CASTLE }]
  };
  var SECOND_RANK = { w: 6, b: 1 };

  function Game(fen) {
    if (!(this instanceof Game)) return new Game(fen);
    this.board = new Array(128);
    this.kings = { w: -1, b: -1 };
    this.turn = WHITE;
    this.castling = { w: 0, b: 0 };
    this.epSquare = -1;
    this.halfMoves = 0;
    this.moveNumber = 1;
    this.history = [];
    this.load(fen || DEFAULT_FEN);
  }

  Game.prototype.clear = function () {
    for (var i = 0; i < 128; i++) this.board[i] = null;
    this.kings = { w: -1, b: -1 };
    this.turn = WHITE;
    this.castling = { w: 0, b: 0 };
    this.epSquare = -1;
    this.halfMoves = 0;
    this.moveNumber = 1;
    this.history = [];
  };

  Game.prototype.load = function (fen) {
    var tokens = fen.split(/\s+/);
    var position = tokens[0];
    this.clear();
    var square = 0;
    for (var i = 0; i < position.length; i++) {
      var piece = position.charAt(i);
      if (piece === '/') { square += 8; continue; }
      if (isDigit(piece)) { square += parseInt(piece, 10); continue; }
      var color = (piece < 'a') ? WHITE : BLACK;
      this.put({ type: piece.toLowerCase(), color: color }, algebraic(square));
      square++;
    }
    this.turn = (tokens[1] === 'b') ? BLACK : WHITE;
    var rights = tokens[2] || '-';
    if (rights.indexOf('K') > -1) this.castling.w |= BITS.KSIDE_CASTLE;
    if (rights.indexOf('Q') > -1) this.castling.w |= BITS.QSIDE_CASTLE;
    if (rights.indexOf('k') > -1) this.castling.b |= BITS.KSIDE_CASTLE;
    if (rights.indexOf('q') > -1) this.castling.b |= BITS.QSIDE_CASTLE;
    this.epSquare = (!tokens[3] || tokens[3] === '-') ? -1 : SQUARES[tokens[3]];
    if (this.epSquare === undefined) this.epSquare = -1;
    this.halfMoves = parseInt(tokens[4], 10); if (isNaN(this.halfMoves)) this.halfMoves = 0;
    this.moveNumber = parseInt(tokens[5], 10); if (isNaN(this.moveNumber)) this.moveNumber = 1;
    return true;
  };

  Game.prototype.fen = function () {
    var out = '', empty = 0;
    for (var i = 0; i <= 119; i++) {
      if (this.board[i] == null) { empty++; }
      else {
        if (empty > 0) { out += empty; empty = 0; }
        var p = this.board[i];
        out += (p.color === WHITE) ? p.type.toUpperCase() : p.type;
      }
      if ((i + 1) & 0x88) {
        if (empty > 0) out += empty;
        if (i !== 119) out += '/';
        empty = 0;
        i += 8;
      }
    }
    var cflags = '';
    if (this.castling.w & BITS.KSIDE_CASTLE) cflags += 'K';
    if (this.castling.w & BITS.QSIDE_CASTLE) cflags += 'Q';
    if (this.castling.b & BITS.KSIDE_CASTLE) cflags += 'k';
    if (this.castling.b & BITS.QSIDE_CASTLE) cflags += 'q';
    if (cflags === '') cflags = '-';
    var ep = (this.epSquare === -1) ? '-' : algebraic(this.epSquare);
    return [out, this.turn, cflags, ep, this.halfMoves, this.moveNumber].join(' ');
  };

  Game.prototype.get = function (square) {
    var sq = SQUARES[square];
    if (sq === undefined) return null;
    var p = this.board[sq];
    return p ? { type: p.type, color: p.color } : null;
  };

  Game.prototype.put = function (piece, square) {
    if ('pnbrqk'.indexOf(piece.type) === -1) return false;
    var sq = SQUARES[square];
    if (sq === undefined) return false;
    if (piece.type === KING && this.kings[piece.color] !== -1 && this.kings[piece.color] !== sq) return false;
    this.board[sq] = { type: piece.type, color: piece.color };
    if (piece.type === KING) this.kings[piece.color] = sq;
    return true;
  };

  Game.prototype.remove = function (square) {
    var sq = SQUARES[square];
    if (sq === undefined) return null;
    var piece = this.board[sq];
    this.board[sq] = null;
    if (piece && piece.type === KING) this.kings[piece.color] = -1;
    return piece;
  };

  function buildMove(board, from, to, flags, promotion) {
    var move = {
      color: board[from].color,
      from: from, to: to, flags: flags,
      piece: board[from].type,
      san: null, promotion: null, captured: null
    };
    if (promotion) { move.flags |= BITS.PROMOTION; move.promotion = promotion; }
    if (board[to]) move.captured = board[to].type;
    else if (flags & BITS.EP_CAPTURE) move.captured = PAWN;
    return move;
  }

  Game.prototype.generateMoves = function (options) {
    var self = this;
    var moves = [];
    var us = this.turn, them = swapColor(us);
    var secondRank = SECOND_RANK[us];
    var legal = !(options && options.legal === false);
    var singleSquare = null;
    if (options && options.square) {
      singleSquare = SQUARES[options.square];
      if (singleSquare === undefined) return [];
    }

    function addMove(from, to, flags) {
      if (self.board[from].type === PAWN && (rankOf(to) === 0 || rankOf(to) === 7)) {
        var promos = [QUEEN, ROOK, BISHOP, KNIGHT];
        for (var k = 0; k < 4; k++) moves.push(buildMove(self.board, from, to, flags, promos[k]));
      } else {
        moves.push(buildMove(self.board, from, to, flags));
      }
    }

    var firstSq = 0, lastSq = 119;
    if (singleSquare !== null) { firstSq = lastSq = singleSquare; }

    for (var i = firstSq; i <= lastSq; i++) {
      if (i & 0x88) { i += 7; continue; }
      var piece = this.board[i];
      if (!piece || piece.color !== us) continue;

      if (piece.type === PAWN) {
        var offs = PAWN_OFFSETS[us];
        var sq = i + offs[0];
        if (!(sq & 0x88) && !this.board[sq]) {
          addMove(i, sq, BITS.NORMAL);
          var sq2 = i + offs[1];
          if (secondRank === rankOf(i) && !(sq2 & 0x88) && !this.board[sq2]) addMove(i, sq2, BITS.BIG_PAWN);
        }
        for (var j = 2; j < 4; j++) {
          var sqc = i + offs[j];
          if (sqc & 0x88) continue;
          if (this.board[sqc] && this.board[sqc].color === them) addMove(i, sqc, BITS.CAPTURE);
          else if (sqc === this.epSquare) addMove(i, sqc, BITS.EP_CAPTURE);
        }
      } else {
        var pieceOffsets = PIECE_OFFSETS[piece.type];
        for (var d = 0; d < pieceOffsets.length; d++) {
          var offset = pieceOffsets[d], square = i;
          while (true) {
            square += offset;
            if (square & 0x88) break;
            if (!this.board[square]) {
              addMove(i, square, BITS.NORMAL);
            } else {
              if (this.board[square].color === them) addMove(i, square, BITS.CAPTURE);
              break;
            }
            if (piece.type === KNIGHT || piece.type === KING) break;
          }
        }
      }
    }

    /* castling is generated when scanning the whole board or the king square */
    if (singleSquare === null || singleSquare === this.kings[us]) {
      if (this.kings[us] !== -1) {
        if (this.castling[us] & BITS.KSIDE_CASTLE) {
          var kFrom = this.kings[us], kTo = kFrom + 2;
          if (!this.board[kFrom + 1] && !this.board[kTo] &&
              !this.attacked(them, kFrom) && !this.attacked(them, kFrom + 1) && !this.attacked(them, kTo)) {
            moves.push(buildMove(this.board, kFrom, kTo, BITS.KSIDE_CASTLE));
          }
        }
        if (this.castling[us] & BITS.QSIDE_CASTLE) {
          var qFrom = this.kings[us], qTo = qFrom - 2;
          if (!this.board[qFrom - 1] && !this.board[qFrom - 2] && !this.board[qFrom - 3] &&
              !this.attacked(them, qFrom) && !this.attacked(them, qFrom - 1) && !this.attacked(them, qTo)) {
            moves.push(buildMove(this.board, qFrom, qTo, BITS.QSIDE_CASTLE));
          }
        }
      }
    }

    if (!legal) return moves;

    var legalMoves = [];
    for (var m = 0; m < moves.length; m++) {
      this.makeMove(moves[m]);
      if (!this.kingAttacked(us)) legalMoves.push(moves[m]);
      this.undoMove();
    }
    return legalMoves;
  };

  Game.prototype.attacked = function (color, square) {
    for (var i = 0; i <= 119; i++) {
      if (i & 0x88) { i += 7; continue; }
      var piece = this.board[i];
      if (!piece || piece.color !== color) continue;
      var diff = 119 + i - square;
      var mask = ATTACKS[diff];
      if (!mask) continue;
      var type = piece.type;
      if (type === PAWN) {
        if (color === WHITE ? (mask & A_PW) : (mask & A_PB)) return true;
        continue;
      }
      if (type === KNIGHT) { if (mask & A_N) return true; continue; }
      if (type === KING) { if (mask & A_K) return true; continue; }
      var bit = (type === BISHOP) ? A_B : (type === ROOK) ? A_R : A_Q;
      if (!(mask & bit)) continue;
      var ray = RAYS[diff], j = i + ray, blocked = false;
      while (j !== square) {
        if (this.board[j]) { blocked = true; break; }
        j += ray;
      }
      if (!blocked) return true;
    }
    return false;
  };

  Game.prototype.kingAttacked = function (color) {
    if (this.kings[color] === -1) return false;
    return this.attacked(swapColor(color), this.kings[color]);
  };

  Game.prototype.makeMove = function (move) {
    var us = this.turn, them = swapColor(us);
    this.history.push({
      move: move,
      kings: { w: this.kings.w, b: this.kings.b },
      turn: this.turn,
      castling: { w: this.castling.w, b: this.castling.b },
      epSquare: this.epSquare,
      halfMoves: this.halfMoves,
      moveNumber: this.moveNumber
    });

    this.board[move.to] = this.board[move.from];
    this.board[move.from] = null;

    if (move.flags & BITS.EP_CAPTURE) {
      this.board[move.to + (us === BLACK ? -16 : 16)] = null;
    }
    if (move.flags & BITS.PROMOTION) {
      this.board[move.to] = { type: move.promotion, color: us };
    }
    if (this.board[move.to].type === KING) {
      this.kings[us] = move.to;
      if (move.flags & BITS.KSIDE_CASTLE) {
        this.board[move.to - 1] = this.board[move.to + 1];
        this.board[move.to + 1] = null;
      } else if (move.flags & BITS.QSIDE_CASTLE) {
        this.board[move.to + 1] = this.board[move.to - 2];
        this.board[move.to - 2] = null;
      }
      this.castling[us] = 0;
    }
    var r;
    for (r = 0; r < 2; r++) {
      if (move.from === ROOKS[us][r].square && (this.castling[us] & ROOKS[us][r].flag)) {
        this.castling[us] ^= ROOKS[us][r].flag;
      }
      if (move.to === ROOKS[them][r].square && (this.castling[them] & ROOKS[them][r].flag)) {
        this.castling[them] ^= ROOKS[them][r].flag;
      }
    }

    this.epSquare = (move.flags & BITS.BIG_PAWN) ? (move.to + (us === WHITE ? 16 : -16)) : -1;

    if (move.piece === PAWN || (move.flags & (BITS.CAPTURE | BITS.EP_CAPTURE))) this.halfMoves = 0;
    else this.halfMoves++;

    if (us === BLACK) this.moveNumber++;
    this.turn = them;
  };

  Game.prototype.undoMove = function () {
    var old = this.history.pop();
    if (!old) return null;
    var move = old.move;
    this.kings = old.kings;
    this.turn = old.turn;
    this.castling = old.castling;
    this.epSquare = old.epSquare;
    this.halfMoves = old.halfMoves;
    this.moveNumber = old.moveNumber;

    var us = this.turn, them = swapColor(us);
    this.board[move.from] = this.board[move.to];
    this.board[move.from].type = move.piece;   /* undo promotion */
    this.board[move.to] = null;

    if (move.flags & BITS.EP_CAPTURE) {
      this.board[move.to + (us === BLACK ? -16 : 16)] = { type: PAWN, color: them };
    } else if (move.captured) {
      this.board[move.to] = { type: move.captured, color: them };
    }
    if (move.flags & BITS.KSIDE_CASTLE) {
      this.board[move.to + 1] = this.board[move.to - 1];
      this.board[move.to - 1] = null;
    } else if (move.flags & BITS.QSIDE_CASTLE) {
      this.board[move.to - 2] = this.board[move.to + 1];
      this.board[move.to + 1] = null;
    }
    return move;
  };

  /* ---------- SAN ---------- */

  function disambiguator(move, moves) {
    var ambiguities = 0, sameRank = 0, sameFile = 0;
    for (var i = 0; i < moves.length; i++) {
      var m = moves[i];
      if (m.piece === move.piece && m.from !== move.from && m.to === move.to) {
        ambiguities++;
        if (rankOf(move.from) === rankOf(m.from)) sameRank++;
        if (fileOf(move.from) === fileOf(m.from)) sameFile++;
      }
    }
    if (!ambiguities) return '';
    var from = algebraic(move.from);
    if (sameRank > 0 && sameFile > 0) return from;
    if (sameFile > 0) return from.charAt(1);
    return from.charAt(0);
  }

  Game.prototype.moveToSan = function (move, moves) {
    var output = '';
    if (move.flags & BITS.KSIDE_CASTLE) output = 'O-O';
    else if (move.flags & BITS.QSIDE_CASTLE) output = 'O-O-O';
    else {
      if (move.piece !== PAWN) output += move.piece.toUpperCase() + disambiguator(move, moves);
      if (move.flags & (BITS.CAPTURE | BITS.EP_CAPTURE)) {
        if (move.piece === PAWN) output += algebraic(move.from).charAt(0);
        output += 'x';
      }
      output += algebraic(move.to);
      if (move.flags & BITS.PROMOTION) output += '=' + move.promotion.toUpperCase();
    }
    this.makeMove(move);
    if (this.kingAttacked(this.turn)) {
      output += this.generateMoves().length === 0 ? '#' : '+';
    }
    this.undoMove();
    return output;
  };

  function strippedSan(san) {
    return String(san).replace(/=/, '').replace(/[+#]?[?!]*$/, '').replace(/0/g, 'O');
  }

  /* ---------- public API ---------- */

  Game.prototype.turnColor = function () { return this.turn; };

  Game.prototype.moves = function (options) {
    options = options || {};
    var moves = this.generateMoves(options);
    var out = [];
    for (var i = 0; i < moves.length; i++) {
      if (options.verbose) out.push(this.makeVerbose(moves[i], moves));
      else out.push(this.moveToSan(moves[i], moves));
    }
    return out;
  };

  Game.prototype.makeVerbose = function (move, moves) {
    var flags = '';
    for (var flag in BITS) {
      if (BITS[flag] & move.flags) flags += ({
        NORMAL: 'n', CAPTURE: 'c', BIG_PAWN: 'b', EP_CAPTURE: 'e',
        PROMOTION: 'p', KSIDE_CASTLE: 'k', QSIDE_CASTLE: 'q'
      })[flag];
    }
    return {
      color: move.color,
      from: algebraic(move.from),
      to: algebraic(move.to),
      piece: move.piece,
      captured: move.captured || undefined,
      promotion: move.promotion || undefined,
      flags: flags,
      san: this.moveToSan(move, moves || this.generateMoves()),
      _internal: move
    };
  };

  /* accepts SAN ("Nf3", "exd5", "O-O"), UCI ("g1f3", "e7e8q") or {from,to,promotion} */
  Game.prototype.findMove = function (input) {
    var moves = this.generateMoves();
    var i, m;
    if (input && typeof input === 'object') {
      for (i = 0; i < moves.length; i++) {
        m = moves[i];
        if (algebraic(m.from) === input.from && algebraic(m.to) === input.to) {
          if (m.flags & BITS.PROMOTION) {
            if (!input.promotion || m.promotion === input.promotion) return m;
          } else return m;
        }
      }
      return null;
    }
    var text = String(input).replace(/\s+/g, '');
    var uci = text.match(/^([a-h][1-8])[-x]?([a-h][1-8])([qrbnQRBN])?$/);
    if (uci) {
      var found = this.findMove({ from: uci[1], to: uci[2], promotion: uci[3] ? uci[3].toLowerCase() : null });
      if (found) return found;
    }
    var want = strippedSan(text);
    for (i = 0; i < moves.length; i++) {
      m = moves[i];
      if (strippedSan(this.moveToSan(m, moves)) === want) return m;
    }
    /* tolerate lowercase piece letters, e.g. "nf3" */
    var relaxed = want.replace(/^([nbrqk])/, function (s) { return s.toUpperCase(); });
    for (i = 0; i < moves.length; i++) {
      m = moves[i];
      if (strippedSan(this.moveToSan(m, moves)) === relaxed) return m;
    }
    /* component match: copes with over- or under-specified disambiguation
       ("Ncb4" when only one knight can move, "Nd7" when two can) */
    var parts = relaxed.match(/^([NBRQK])?([a-h])?([1-8])?[x-]?([a-h][1-8])=?([NBRQ])?$/);
    if (parts) {
      var wantPiece = parts[1] ? parts[1].toLowerCase() : PAWN;
      var candidates = [];
      for (i = 0; i < moves.length; i++) {
        m = moves[i];
        if (m.piece !== wantPiece) continue;
        if (algebraic(m.to) !== parts[4]) continue;
        if (parts[2] && algebraic(m.from).charAt(0) !== parts[2]) continue;
        if (parts[3] && algebraic(m.from).charAt(1) !== parts[3]) continue;
        if (parts[5] && m.promotion !== parts[5].toLowerCase()) continue;
        if (!parts[5] && (m.flags & BITS.PROMOTION) && m.promotion !== QUEEN) continue;
        candidates.push(m);
      }
      if (candidates.length === 1) return candidates[0];
    }
    return null;
  };

  Game.prototype.move = function (input) {
    var moves = this.generateMoves();
    var move = this.findMove(input);
    if (!move) return null;
    var verbose = this.makeVerbose(move, moves);
    verbose.before = this.fen();
    this.makeMove(move);
    verbose.after = this.fen();
    this.history[this.history.length - 1].san = verbose.san;
    return verbose;
  };

  Game.prototype.undo = function () {
    var move = this.undoMove();
    return move ? { from: algebraic(move.from), to: algebraic(move.to), piece: move.piece } : null;
  };


  Game.prototype.historySan = function () {
    var out = [];
    for (var i = 0; i < this.history.length; i++) out.push(this.history[i].san || '?');
    return out;
  };

  Game.prototype.lastMove = function () {
    if (!this.history.length) return null;
    var m = this.history[this.history.length - 1].move;
    return { from: algebraic(m.from), to: algebraic(m.to) };
  };

  Game.prototype.inCheck = function () { return this.kingAttacked(this.turn); };
  Game.prototype.isCheckmate = function () { return this.inCheck() && this.generateMoves().length === 0; };
  Game.prototype.isStalemate = function () { return !this.inCheck() && this.generateMoves().length === 0; };

  Game.prototype.insufficientMaterial = function () {
    var pieces = {}, bishops = [], numPieces = 0, sqColor = 0;
    for (var i = 0; i <= 119; i++) {
      if (i & 0x88) { i += 7; continue; }
      sqColor = (sqColor + 1) % 2;
      var piece = this.board[i];
      if (!piece) continue;
      pieces[piece.type] = (pieces[piece.type] || 0) + 1;
      if (piece.type === BISHOP) bishops.push((rankOf(i) + fileOf(i)) % 2);
      numPieces++;
    }
    if (numPieces === 2) return true;
    if (numPieces === 3 && (pieces[BISHOP] === 1 || pieces[KNIGHT] === 1)) return true;
    if (numPieces === pieces[BISHOP] + 2) {
      var sum = 0;
      for (var b = 0; b < bishops.length; b++) sum += bishops[b];
      if (sum === 0 || sum === bishops.length) return true;
    }
    return false;
  };

  Game.prototype.isDraw = function () {
    return this.halfMoves >= 100 || this.isStalemate() || this.insufficientMaterial();
  };
  Game.prototype.isGameOver = function () { return this.isCheckmate() || this.isDraw(); };

  Game.prototype.clone = function () { return new Game(this.fen()); };

  Game.prototype.piecesMap = function () {
    var map = {};
    for (var i = 0; i <= 119; i++) {
      if (i & 0x88) { i += 7; continue; }
      if (this.board[i]) map[algebraic(i)] = { type: this.board[i].type, color: this.board[i].color };
    }
    return map;
  };

  Game.prototype.destinationsMap = function () {
    var moves = this.generateMoves(), map = {};
    for (var i = 0; i < moves.length; i++) {
      var from = algebraic(moves[i].from), to = algebraic(moves[i].to);
      if (!map[from]) map[from] = [];
      var seen = false;
      for (var j = 0; j < map[from].length; j++) if (map[from][j] === to) seen = true;
      if (!seen) map[from].push(to);
    }
    return map;
  };

  Game.prototype.ascii = function () {
    var s = '';
    for (var r = 0; r < 8; r++) {
      s += (8 - r) + ' ';
      for (var f = 0; f < 8; f++) {
        var p = this.board[r * 16 + f];
        s += p ? (p.color === WHITE ? p.type.toUpperCase() : p.type) : '.';
        s += ' ';
      }
      s += '\n';
    }
    s += '  a b c d e f g h\n';
    return s;
  };

  Game.prototype.perft = function (depth) {
    var moves = this.generateMoves({ legal: false });
    var nodes = 0, us = this.turn;
    for (var i = 0; i < moves.length; i++) {
      this.makeMove(moves[i]);
      if (!this.kingAttacked(us)) {
        nodes += (depth - 1 > 0) ? this.perft(depth - 1) : 1;
      }
      this.undoMove();
    }
    return nodes;
  };

  /* ---------- static helpers ---------- */

  Game.SQUARES = (function () {
    var list = [];
    for (var r = 8; r >= 1; r--) for (var f = 0; f < 8; f++) list.push('abcdefgh'.charAt(f) + r);
    return list;
  })();
  Game.DEFAULT_FEN = DEFAULT_FEN;
  Game.squareColor = function (name) {
    var f = 'abcdefgh'.indexOf(String(name).charAt(0));
    var r = parseInt(String(name).charAt(1), 10) - 1;
    if (f < 0 || isNaN(r)) return null;
    return ((f + r) % 2 === 0) ? 'dark' : 'light';
  };
  Game.isSquare = function (name) { return /^[a-h][1-8]$/.test(String(name)); };
  Game.fileOf = function (name) { return 'abcdefgh'.indexOf(String(name).charAt(0)); };
  Game.rankOf = function (name) { return parseInt(String(name).charAt(1), 10) - 1; };
  Game.squareAt = function (file, rank) {
    if (file < 0 || file > 7 || rank < 0 || rank > 7) return null;
    return 'abcdefgh'.charAt(file) + (rank + 1);
  };
  Game.PIECE_NAMES = { p: 'Pawn', n: 'Knight', b: 'Bishop', r: 'Rook', q: 'Queen', k: 'King' };

  global.Chess = Game;
  if (typeof module !== 'undefined' && module.exports) module.exports = Game;

})(typeof window !== 'undefined' ? window : this);
