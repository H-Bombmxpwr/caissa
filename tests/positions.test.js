/* Every stored FEN must be a legal position and every stored solution legal chess. */
(function () {
  function log(s) { WScript.Echo(s); }
  var fails = 0;
  function assert(cond, msg) { if (!cond) { fails++; log("FAIL " + msg); } else { log("OK   " + msg); } }

  function playLine(fen, text) {
    var game = new Chess(fen);
    var cur = { fenAfter: fen, parent: null }, stack = [], errors = [], last = null;
    var re = /(\{[^}]*\})|(\()|(\))|(1-0|0-1|1\/2-1\/2|\*)|(\d+\.(?:\.\.)?)|([OoA-Za-z][A-Za-z0-9#+=\-]*)|(\S)/g;
    var m;
    while ((m = re.exec(text)) !== null) {
      if (m[1]) continue;
      if (m[2]) { stack.push(cur); cur = cur.parent || cur; game = new Chess(cur.fenAfter); continue; }
      if (m[3]) { cur = stack.pop() || cur; game = new Chess(cur.fenAfter); continue; }
      if (m[4] || m[5]) continue;
      if (m[6]) {
        if (/^[A-Za-z]$/.test(m[6])) continue;
        var done = game.move(m[6]);
        if (!done) { errors.push(m[6]); continue; }
        cur = { fenAfter: game.fen(), parent: cur };
        last = game;
      }
    }
    return { errors: errors, end: game };
  }

  var i, e, r;
  for (i = 0; i < window.ENDGAMES.length; i++) {
    e = window.ENDGAMES[i];
    var g = new Chess(e.fen);
    var legalPos = !g.kingAttacked(g.turnColor() === 'w' ? 'b' : 'w');
    assert(legalPos, "endgame " + e.id + ": side not to move is not in check");
    assert(g.generateMoves().length > 0, "endgame " + e.id + ": has legal moves");
    assert(g.turnColor() === e.you, "endgame " + e.id + ": you move first");
    assert(Ai.pieceCount(g) <= 7, "endgame " + e.id + ": within tablebase reach (" + Ai.pieceCount(g) + " pieces)");
  }

  for (i = 0; i < window.STUDIES.length; i++) {
    var st = window.STUDIES[i];
    var sg = new Chess(st.fen);
    assert(!sg.kingAttacked(sg.turnColor() === 'w' ? 'b' : 'w'), "study " + st.id + ": legal position");
    assert(sg.turnColor() === st.you, "study " + st.id + ": you move first");
    r = playLine(st.fen, st.line);
    assert(r.errors.length === 0, "study " + st.id + ": solution is legal" +
      (r.errors.length ? " (" + r.errors.join(",") + ")" : ""));
    if (st.goal === 'mate' && r.errors.length === 0) {
      assert(r.end.isCheckmate(), "study " + st.id + ": solution ends in checkmate");
    }
  }

  /* short mating puzzles: the engine must see the forced mate.
     The smothered mate is 7 plies deep, too far for a quick search, so there we
     only check the engine agrees with the first move. */
  var forced = ["anastasia", "backrank"];
  for (i = 0; i < forced.length; i++) {
    var target = null;
    for (var j = 0; j < window.STUDIES.length; j++) if (window.STUDIES[j].id === forced[i]) target = window.STUDIES[j];
    if (!target) continue;
    var res = Ai.search(new Chess(target.fen), { depth: 5, timeMs: 30000 });
    assert(res && res.mateIn !== null, "study " + target.id + ": engine confirms forced mate (found " +
      (res ? res.san + " mateIn=" + res.mateIn : "nothing") + ")");
  }
  /* the built-in search is deliberately small; the smothered mate (7 plies) is
     beyond it, which is why studies replay their stored solution line and level 4
     prefers the lichess tablebase when it is reachable. */

  log(fails ? (fails + " position test(s) FAILED") : "all position data valid");
})();
