/* AI sanity checks */
(function () {
  function log(s) { WScript.Echo(s); }
  var fails = 0;
  function assert(cond, msg) { if (!cond) { fails++; log("FAIL " + msg); } else { log("OK   " + msg); } }

  var g1 = new Chess("7k/5Q2/6K1/8/8/8/8/8 w - - 0 1");
  var r1 = Ai.search(g1, { depth: 3 });
  assert(r1 && /#$/.test(r1.san), "finds mate in 1 (got " + (r1 && r1.san) + ")");

  var g2 = new Chess("8/8/8/4k3/8/8/3QK3/8 w - - 0 1");
  var r2 = Ai.search(g2, { depth: 4, timeMs: 5000 });
  assert(r2 && g2.findMove(r2.san) !== null, "returns a legal move in KQ v K (" + (r2 && r2.san) + ")");

  var g4 = new Chess("6k1/8/5K2/8/8/8/7R/8 b - - 0 1");
  var r4 = Ai.search(g4, { depth: 4, timeMs: 5000 });
  assert(r4 && r4.san === "Kf8", "defender finds the only legal move Kf8 (got " + (r4 && r4.san) + ")");

  /* defender should not walk into a mate in 1 when it has a choice */
  var g5 = new Chess("7k/8/6K1/8/8/8/8/6R1 b - - 0 1");
  var r5 = Ai.search(g5, { depth: 4, timeMs: 5000 });
  assert(r5 && r5.san !== "Kh7", "defender avoids the square that allows instant mate (got " + (r5 && r5.san) + ")");

  var e1 = Ai.evaluate(new Chess("4k3/8/8/8/8/8/8/3QK3 w - - 0 1"));
  var e2 = Ai.evaluate(new Chess("3qk3/8/8/8/8/8/8/4K3 w - - 0 1"));
  assert(e1 > 500 && e2 < -500, "eval signed from White's view (" + e1 + " / " + e2 + ")");

  var t0 = new Date().getTime();
  var r6 = Ai.search(new Chess("8/8/8/3k4/8/8/4KP2/8 w - - 0 1"), { depth: 5, timeMs: 4000 });
  log("     depth-5 pawn ending: " + (r6 && r6.san) + " in " + (new Date().getTime() - t0) + "ms");

  log(fails ? (fails + " AI test(s) FAILED") : "all AI tests passed");
})();
