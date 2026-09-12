/* Small endgame engine: alpha-beta with an endgame-aware eval, used to give the
 * defending side real resistance. Written in ES5 so it can be unit-tested headlessly.
 * When online, the lichess tablebase is preferred for <= 7 pieces (perfect play). */
(function (global) {
  'use strict';

  var VALUES = { p: 100, n: 320, b: 330, r: 500, q: 900, k: 0 };
  var MATE = 100000;

  function pieceCount(game) {
    var map = game.piecesMap(), n = 0;
    for (var k in map) if (map.hasOwnProperty(k)) n++;
    return n;
  }

  function fileIdx(sq) { return 'abcdefgh'.indexOf(sq.charAt(0)); }
  function rankIdx(sq) { return parseInt(sq.charAt(1), 10) - 1; }

  function centerDistance(sq) {
    var f = fileIdx(sq), r = rankIdx(sq);
    var df = Math.max(3 - f, f - 4), dr = Math.max(3 - r, r - 4);
    return df + dr;
  }

  function manhattan(a, b) {
    return Math.abs(fileIdx(a) - fileIdx(b)) + Math.abs(rankIdx(a) - rankIdx(b));
  }

  /* score from White's point of view */
  function evaluate(game) {
    var map = game.piecesMap();
    var score = 0, key;
    var material = { w: 0, b: 0 }, pawns = { w: [], b: [] }, kings = { w: null, b: null };

    for (key in map) {
      if (!map.hasOwnProperty(key)) continue;
      var p = map[key];
      material[p.color] += VALUES[p.type];
      if (p.type === 'p') pawns[p.color].push(key);
      if (p.type === 'k') kings[p.color] = key;
    }
    score += material.w - material.b;

    /* pawn advancement + king support */
    for (var i = 0; i < pawns.w.length; i++) {
      var wsq = pawns.w[i];
      score += (rankIdx(wsq) - 1) * 12;
      if (kings.w) score -= manhattan(kings.w, wsq) * 3;
      if (kings.b) score += manhattan(kings.b, wsq) * 2;
    }
    for (var j = 0; j < pawns.b.length; j++) {
      var bsq = pawns.b[j];
      score -= (6 - rankIdx(bsq)) * 12;
      if (kings.b) score += manhattan(kings.b, bsq) * 3;
      if (kings.w) score -= manhattan(kings.w, bsq) * 2;
    }

    /* mating logic: the side that is clearly ahead drives the enemy king to the edge */
    var diff = material.w - material.b;
    if (Math.abs(diff) > 250 && kings.w && kings.b) {
      var strong = diff > 0 ? 'w' : 'b';
      var weakKing = strong === 'w' ? kings.b : kings.w;
      var strongKing = strong === 'w' ? kings.w : kings.b;
      var drive = centerDistance(weakKing) * 14 + (14 - manhattan(strongKing, weakKing)) * 8;
      score += (strong === 'w') ? drive : -drive;
    }
    return score;
  }

  function orderMoves(game, moves) {
    var scored = [];
    for (var i = 0; i < moves.length; i++) {
      var m = moves[i], s = 0;
      if (m.captured) s += 10 * VALUES[m.captured] - VALUES[m.piece];
      if (m.flags & 16) s += 800;       // promotion
      scored.push({ m: m, s: s });
    }
    scored.sort(function (a, b) { return b.s - a.s; });
    var out = [];
    for (var j = 0; j < scored.length; j++) out.push(scored[j].m);
    return out;
  }

  function quiesce(game, alpha, beta, ply, side) {
    var stand = evaluate(game) * side;
    if (stand >= beta) return beta;
    if (stand > alpha) alpha = stand;
    var moves = game.generateMoves();
    var caps = [];
    for (var i = 0; i < moves.length; i++) if (moves[i].captured) caps.push(moves[i]);
    caps = orderMoves(game, caps);
    for (var c = 0; c < caps.length; c++) {
      game.makeMove(caps[c]);
      var score = -quiesce(game, -beta, -alpha, ply + 1, -side);
      game.undoMove();
      if (score >= beta) return beta;
      if (score > alpha) alpha = score;
    }
    return alpha;
  }

  function negamax(game, depth, alpha, beta, ply, side, deadline) {
    if (deadline && ply > 1 && (new Date()).getTime() > deadline) return evaluate(game) * side;
    var moves = game.generateMoves();
    if (!moves.length) {
      if (game.inCheck()) return -(MATE - ply);
      return 0;
    }
    if (game.halfMoves >= 100) return 0;
    if (depth <= 0) return quiesce(game, alpha, beta, ply, side);

    moves = orderMoves(game, moves);
    var best = -Infinity;
    for (var i = 0; i < moves.length; i++) {
      game.makeMove(moves[i]);
      var score = -negamax(game, depth - 1, -beta, -alpha, ply + 1, -side, deadline);
      game.undoMove();
      if (score > best) best = score;
      if (score > alpha) alpha = score;
      if (alpha >= beta) break;
    }
    return best;
  }

  /* returns { san, from, to, score, depth } */
  function search(fenOrGame, options) {
    options = options || {};
    var game = (typeof fenOrGame === 'string') ? new Chess(fenOrGame) : fenOrGame.clone();
    var maxDepth = options.depth || 4;
    var deadline = options.timeMs ? (new Date()).getTime() + options.timeMs : 0;
    var side = game.turnColor() === 'w' ? 1 : -1;
    var legal = game.generateMoves();
    if (!legal.length) return null;

    var bestMove = legal[0], bestScore = -Infinity, reached = 0;
    for (var depth = 1; depth <= maxDepth; depth++) {
      var localBest = null, localScore = -Infinity;
      var moves = orderMoves(game, game.generateMoves());
      for (var i = 0; i < moves.length; i++) {
        game.makeMove(moves[i]);
        var score = -negamax(game, depth - 1, -Infinity, Infinity, 1, -side, deadline);
        game.undoMove();
        if (score > localScore) { localScore = score; localBest = moves[i]; }
      }
      if (localBest) { bestMove = localBest; bestScore = localScore; reached = depth; }
      if (deadline && (new Date()).getTime() > deadline) break;
      if (Math.abs(bestScore) > MATE - 100) break;
    }

    var all = game.generateMoves();
    var san = game.moveToSan(bestMove, all);
    return {
      san: san,
      from: 'abcdefgh'.charAt(bestMove.from & 15) + (8 - (bestMove.from >> 4)),
      to: 'abcdefgh'.charAt(bestMove.to & 15) + (8 - (bestMove.to >> 4)),
      score: bestScore,
      depth: reached,
      mateIn: Math.abs(bestScore) > MATE - 100 ? Math.ceil((MATE - Math.abs(bestScore)) / 2) : null
    };
  }

  /* Lichess 7-piece tablebase — perfect play when we can reach it. */
  function tablebase(fen) {
    return fetch('https://tablebase.lichess.ovh/standard?fen=' + encodeURIComponent(fen))
      .then(function (r) {
        if (!r.ok) throw new Error('tablebase ' + r.status);
        return r.json();
      });
  }

  function bestMoveAsync(game, options) {
    options = options || {};
    var fen = game.fen();
    var local = function () { return search(game, options); };
    if (options.useTablebase === false || pieceCount(game) > 7 || typeof fetch !== 'function') {
      return Promise.resolve(local());
    }
    /* note: .then(ok, fail) rather than .catch() so this file stays ES3-parsable
       for the headless test runner */
    return tablebase(fen).then(function (data) {
      if (!data || !data.moves || !data.moves.length) return local();
      var chosen = data.moves[0];      // API sorts best-for-side-to-move first
      var found = game.findMove(chosen.uci);
      if (!found) return local();
      return {
        san: chosen.san,
        from: chosen.uci.slice(0, 2),
        to: chosen.uci.slice(2, 4),
        tablebase: true,
        category: data.category,
        dtz: data.dtz,
        dtm: data.dtm,
        mateIn: chosen.dtm ? Math.ceil(Math.abs(chosen.dtm) / 2) : null
      };
    }, function () { return local(); });
  }

  /* Pick the strongest opponent available:
   *   1. lichess tablebase  — perfect play, <= 7 pieces, needs the network
   *   2. Stockfish          — needs the page served over http(s)
   *   3. the search above    — always there
   * Returns a promise of { san, from, to, source }. */
  function reply(game, options) {
    options = options || {};
    var wantTb = options.useTablebase !== false && pieceCount(game) <= 7 && typeof fetch === 'function';
    var wantSf = options.useStockfish !== false &&
      typeof global.Stockfish !== 'undefined' && global.Stockfish.supported();

    function viaStockfish() {
      if (!wantSf) return Promise.resolve(null);
      return global.Stockfish.bestMove(game, {
        movetime: options.movetime || 500,
        skill: options.skill
      }).then(function (res) {
        if (!res) return null;
        res.source = 'stockfish';
        return res;
      }, function () { return null; });
    }

    function viaSearch() {
      var res = search(game, { depth: options.depth || 4, timeMs: options.timeMs || 1500 });
      if (res) res.source = 'builtin';
      return res;
    }

    var chain;
    if (wantTb) {
      chain = tablebase(game.fen()).then(function (data) {
        if (!data || !data.moves || !data.moves.length) return null;
        var chosen = data.moves[0];
        if (!game.findMove(chosen.uci)) return null;
        return {
          san: chosen.san,
          from: chosen.uci.slice(0, 2),
          to: chosen.uci.slice(2, 4),
          source: 'tablebase',
          category: data.category,
          dtz: data.dtz,
          dtm: chosen.dtm,
          mateIn: chosen.dtm ? Math.ceil(Math.abs(chosen.dtm) / 2) : null
        };
      }, function () { return null; });
    } else {
      chain = Promise.resolve(null);
    }

    return chain.then(function (res) {
      if (res) return res;
      return viaStockfish();
    }).then(function (res) {
      return res || viaSearch();
    });
  }

  global.Ai = {
    reply: reply,
    evaluate: evaluate,
    search: search,
    tablebase: tablebase,
    bestMoveAsync: bestMoveAsync,
    pieceCount: pieceCount,
    MATE: MATE
  };
  if (typeof module !== 'undefined' && module.exports) module.exports = global.Ai;
})(typeof window !== 'undefined' ? window : this);
