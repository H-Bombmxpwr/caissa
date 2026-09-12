/* Every built-in opening line must be legal chess, variations included */
(function () {
  function log(s) { WScript.Echo(s); }
  var fails = 0;
  function walk(pgn) {
    var start = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";
    var root = { fenAfter: start, parent: null, san: null };
    var game = new Chess(start), cur = root, stack = [], errors = [], plies = 0, vars = 0;
    var re = /(\{[^}]*\})|(\()|(\))|(\$\d+)|(1-0|0-1|1\/2-1\/2|\*)|(\d+\.(?:\.\.)?)|([OoA-Za-z][A-Za-z0-9#+=\-]*)|(\S)/g;
    var m;
    while ((m = re.exec(pgn)) !== null) {
      if (m[1]) continue;
      if (m[2]) { stack.push(cur); cur = cur.parent || root; game = new Chess(cur.fenAfter); vars++; continue; }
      if (m[3]) { cur = stack.pop() || root; game = new Chess(cur.fenAfter); continue; }
      if (m[4] || m[5] || m[6]) continue;
      if (m[7]) {
        if (/^[A-Za-z]$/.test(m[7])) continue;
        var done = game.move(m[7]);
        if (!done) { errors.push(m[7] + " after " + (cur.san || "start")); continue; }
        cur = { fenAfter: game.fen(), parent: cur, san: done.san };
        plies++;
      }
    }
    return { errors: errors, plies: plies, vars: vars };
  }
  for (var i = 0; i < window.OPENINGS.length; i++) {
    var o = window.OPENINGS[i], r = walk(o.pgn);
    if (r.errors.length) { fails++; log("FAIL " + o.id + " -> " + r.errors.join(" | ")); }
    else log("OK   " + o.id + " (" + r.plies + " plies, " + r.vars + " variations)");
  }
  log(fails ? (fails + " opening(s) FAILED") : "all openings legal");
})();
