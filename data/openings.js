/* Opening lines for level 3. Variations are the opponent deviations you must punish. */
window.OPENINGS = [
  {
    id: 'italian',
    name: 'Italian Game — Giuoco Pianissimo',
    side: 'w',
    eco: 'C50',
    note: 'Slow Italian setup. Black may try 3...Nf6 (Two Knights) or grab with 4...Nxe4.',
    pgn: '1. e4 e5 2. Nf3 Nc6 3. Bc4 Bc5 (3... Nf6 4. d3 Bc5 5. c3 d6 6. O-O) 4. c3 Nf6 ' +
      '(4... Qe7 5. d4 Bb6) 5. d3 d6 6. O-O O-O 7. Re1 a6 8. Nbd2 Ba7 9. h3'
  },
  {
    id: 'ruy',
    name: 'Ruy Lopez — Closed, Main Line',
    side: 'w',
    eco: 'C92',
    note: 'The main highway: 9.h3 before d4. Watch the Noah\'s Ark trap if you play an early d4.',
    pgn: '1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 4. Ba4 Nf6 (4... d6 5. c3 Bd7 6. d4 Nf6 7. O-O) ' +
      '5. O-O Be7 6. Re1 b5 7. Bb3 d6 8. c3 O-O 9. h3 Na5 10. Bc2 c5 11. d4 Qc7'
  },
  {
    id: 'najdorf',
    name: 'Sicilian Najdorf — English Attack',
    side: 'b',
    eco: 'B90',
    note: 'You are Black. Know the move order: ...a6 first, then meet 6.Be3 with 6...e5.',
    pgn: '1. e4 c5 2. Nf3 d6 3. d4 cxd4 4. Nxd4 Nf6 5. Nc3 a6 6. Be3 (6. Bg5 e6 7. f4 Be7) ' +
      '(6. Be2 e5 7. Nb3 Be7) e5 7. Nb3 Be6 8. f3 Be7 9. Qd2 O-O 10. O-O-O Nbd7'
  },
  {
    id: 'french-winawer',
    name: 'French Defense — Winawer',
    side: 'b',
    eco: 'C18',
    note: 'You are Black. The pin, the doubled c-pawns, and the ...Qc7 counterplay.',
    pgn: '1. e4 e6 2. d4 d5 3. Nc3 (3. Nd2 c5 4. exd5 exd5 5. Ngf3 Nc6) Bb4 4. e5 c5 5. a3 Bxc3+ ' +
      '6. bxc3 Ne7 7. Qg4 Qc7 8. Qxg7 Rg8 9. Qxh7 cxd4 10. Ne2 Nbc6'
  },
  {
    id: 'qgd',
    name: "Queen's Gambit Declined — Orthodox",
    side: 'w',
    eco: 'D35',
    note: 'Classical development with Bg5 and the Exchange structure.',
    pgn: '1. d4 d5 2. c4 e6 (2... c6 3. Nf3 Nf6 4. Nc3 dxc4 5. a4 Bf5) 3. Nc3 Nf6 4. Bg5 Be7 ' +
      '5. e3 O-O 6. Nf3 h6 7. Bh4 b6 8. cxd5 Nxd5 9. Bxe7 Qxe7 10. Nxd5 exd5'
  },
  {
    id: 'caro-advance',
    name: 'Caro-Kann — Advance Variation',
    side: 'b',
    eco: 'B12',
    note: 'You are Black: get the light-squared bishop out before ...e6.',
    pgn: '1. e4 c6 2. d4 d5 3. e5 (3. Nc3 dxe4 4. Nxe4 Bf5 5. Ng3 Bg6 6. h4 h6) Bf5 ' +
      '4. Nf3 e6 5. Be2 c5 6. Be3 Qb6 7. Nc3 Ne7 8. O-O Nbc6 9. dxc5 Qxc5'
  },
  {
    id: 'legal',
    name: "Trap — Légal's Mate",
    side: 'w',
    eco: 'C41',
    note: 'The queen sacrifice only works because of the pin on the e-file. Black can decline with 6...dxe5.',
    pgn: '1. e4 e5 2. Nf3 Nc6 3. Bc4 d6 4. Nc3 Bg4 5. h3 Bh5 6. Nxe5 Bxd1 (6... Nxe5 7. Qxh5 Nxc4 8. Qb5+ c6 9. Qxc4) ' +
      '7. Bxf7+ Ke7 8. Nd5#'
  },
  {
    id: 'fried-liver',
    name: 'Trap — Fried Liver Attack',
    side: 'w',
    eco: 'C57',
    note: 'After 5...Nxd5?! the knight sacrifice drags the king out. 5...Na5 is the sane defense.',
    pgn: '1. e4 e5 2. Nf3 Nc6 3. Bc4 Nf6 4. Ng5 d5 5. exd5 Nxd5 (5... Na5 6. Bb5+ c6 7. dxc6 bxc6 8. Be2 h6 9. Nf3 e4) ' +
      '6. Nxf7 Kxf7 7. Qf3+ Ke6 8. Nc3 Ncb4 9. Qe4'
  },
  {
    id: 'shilling',
    name: 'Trap — Blackburne Shilling',
    side: 'b',
    eco: 'C50',
    note: 'You are Black. 4.Nxe5?? loses on the spot; know the refutation of 4.Nxd4 too.',
    pgn: '1. e4 e5 2. Nf3 Nc6 3. Bc4 Nd4 4. Nxe5 (4. Nxd4 exd4 5. O-O Ne7 6. d3 Ng6) ' +
      'Qg5 5. Nxf7 Qxg2 6. Rf1 Qxe4+ 7. Be2 Nf3#'
  },
  {
    id: 'noahs-ark',
    name: "Trap — Noah's Ark (Ruy Lopez)",
    side: 'b',
    eco: 'C70',
    note: 'You are Black. The pawns roll forward and the bishop drowns on b3.',
    pgn: '1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 4. Ba4 d6 5. d4 b5 6. Bb3 Nxd4 7. Nxd4 exd4 8. Qxd4 c5 9. Qd5 Be6 10. Qc6+ Bd7 11. Qd5 c4'
  },
  {
    id: 'scandinavian',
    name: 'Scandinavian — 3...Qa5',
    side: 'b',
    eco: 'B01',
    note: 'You are Black. Simple, forcing, easy to memorize — ideal first blindfold repertoire line.',
    pgn: '1. e4 d5 2. exd5 Qxd5 3. Nc3 Qa5 4. d4 Nf6 5. Nf3 c6 6. Bc4 Bf5 7. Bd2 e6 8. Qe2 Bb4 9. O-O-O Nbd7'
  },
  {
    id: 'london',
    name: 'London System',
    side: 'w',
    eco: 'D02',
    note: 'Same setup against almost anything: Bf4, e3, c3, Nbd2, Bd3, h3.',
    pgn: '1. d4 d5 2. Bf4 Nf6 3. e3 e6 (3... c5 4. c3 Nc6 5. Nd2 Bf5 6. Ngf3 e6) 4. Nf3 Bd6 5. Bg3 O-O ' +
      '6. Bd3 b6 7. Nbd2 Bb7 8. c3 Nbd7 9. Ne5'
  }
];
