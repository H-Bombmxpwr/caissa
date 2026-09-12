/* Move generation (perft) and SAN round-trips */
(function () {
  function log(s) { WScript.Echo(s); }
  var fails = 0;
  function assert(cond, msg) { if (!cond) { fails++; log("FAIL " + msg); } else { log("OK   " + msg); } }

  function perft(name, fen, expected) {
    var g = new Chess(fen);
    for (var d = 1; d <= expected.length; d++) {
      var n = g.perft(d);
      assert(n === expected[d - 1], "perft " + name + " d" + d + " = " + n + " (want " + expected[d - 1] + ")");
    }
  }
  perft("startpos", "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1", [20, 400, 8902, 197281]);
  perft("kiwipete", "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1", [48, 2039, 97862]);
  perft("ep/promo", "8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1", [14, 191, 2812, 43238]);
  perft("pos4", "r3k2r/Pppp1ppp/1b3nbN/nP6/BBP1P3/q4N2/Pp1P2PP/R2Q1RK1 w kq - 0 1", [6, 264, 9467]);
  perft("pos5", "rnbq1k1r/pp1Pbppp/2p5/8/2B5/8/PPP1NnPP/RNBQK2R w KQ - 1 8", [44, 1486, 62379]);

  var g = new Chess();
  var line = "e4 e5 Nf3 Nc6 Bb5 a6 Ba4 Nf6 O-O Be7 Re1 b5 Bb3 d6 c3 O-O h3 Na5 Bc2 c5 d4 Qc7".split(" ");
  var ok = true;
  for (var i = 0; i < line.length; i++) {
    var m = g.move(line[i]);
    if (!m || m.san !== line[i]) { ok = false; break; }
  }
  assert(ok, "SAN round-trip through a Ruy Lopez line");
  assert(g.fen() === "r1b2rk1/2q1bppp/p2p1n2/npp1p3/3PP3/2P2N1P/PPB2PP1/RNBQR1K1 w - - 1 12", "FEN after the line");

  var ep = new Chess("k7/8/8/3pP3/8/8/8/K7 w - d6 0 2");
  assert(ep.move("exd6") !== null && ep.fen().indexOf("3P4") > -1, "en passant capture");

  var cas = new Chess("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1");
  assert(cas.move("O-O-O") !== null && cas.fen().indexOf("2KR3R") > -1, "queenside castling");

  var pro = new Chess("8/PK6/8/8/8/8/7k/8 w - - 0 1");
  assert(pro.moves().join(" ").indexOf("a8=N") > -1, "underpromotions generated");

  var uci = new Chess();
  assert(uci.move("g1f3").san === "Nf3", "UCI input accepted");

  var dis = new Chess("8/8/8/8/K7/8/6k1/R6R w - - 0 1");
  assert(dis.findMove("Rab1") !== null && dis.findMove("Rhb1") !== null, "explicit rook disambiguation");
  assert(dis.findMove("Rb1") === null, "ambiguous Rb1 is rejected");

  /* over-specified disambiguation, as real PGN often writes it: only one knight
     can legally move (the other is pinned), yet the file is given anyway */
  var over = new Chess("r1bq1b1r/ppp3pp/2n1kn2/3p4/2B5/2N2Q2/PPPP1PPP/R1B1K2R b KQ - 1 8");
  assert(over.findMove("Ncb4") !== null, "over-specified disambiguation accepted");

  var mate = new Chess("6k1/5ppp/8/8/8/8/8/R5K1 w - - 0 1");
  mate.move("Ra8");
  assert(mate.isCheckmate() && mate.historySan()[0] === "Ra8#", "back-rank mate detected and annotated");

  var stale = new Chess("7k/5Q2/6K1/8/8/8/8/8 b - - 0 1");
  assert(stale.isStalemate() === true && stale.inCheck() === false, "Qf7 stalemate recognized");
  var notStale = new Chess("7k/8/6K1/8/8/8/8/6R1 b - - 0 1");
  assert(notStale.isStalemate() === false, "position with legal replies is not stalemate");

  var insuf = new Chess("8/8/4k3/8/8/3KB3/8/8 w - - 0 1");
  assert(insuf.insufficientMaterial() === true, "K+B vs K is insufficient material");

  log(fails ? (fails + " engine test(s) FAILED") : "all engine tests passed");
})();
