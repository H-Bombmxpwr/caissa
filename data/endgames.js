/* Theoretical endings for level 4. You play `you`; the app defends. */
window.ENDGAMES = [
  {
    id: 'kq-k',
    name: 'Queen mate (K+Q vs K)',
    fen: '4k3/8/8/8/8/8/3Q4/4K3 w - - 0 1',
    you: 'w',
    goal: 'mate',
    par: 10,
    note: 'Box the king in with the queen a knight\'s move away, walk your king up, then mate. ' +
      'Beware stalemate.'
  },
  {
    id: 'kr-k',
    name: 'Rook mate (K+R vs K)',
    fen: '4k3/8/8/8/8/8/3R4/4K3 w - - 0 1',
    you: 'w',
    goal: 'mate',
    par: 16,
    note: 'Cut the king off, take the opposition, then shrink the box rank by rank.'
  },
  {
    id: 'kbb-k',
    name: 'Two bishops mate',
    fen: '4k3/8/8/8/8/8/2BB4/4K3 w - - 0 1',
    you: 'w',
    goal: 'mate',
    par: 20,
    note: 'Build the diagonal wall, push the king to a corner — any corner — with the king helping.'
  },
  {
    id: 'kbn-k',
    name: 'Bishop and knight mate',
    fen: '4k3/8/8/8/8/8/3BN3/4K3 w - - 0 1',
    you: 'w',
    goal: 'mate',
    par: 33,
    note: 'The hard one. Drive the king to a corner of the bishop\'s color; remember the W-maneuver ' +
      'with the knight.'
  },
  {
    id: 'q-vs-r',
    name: 'Queen vs Rook',
    fen: '8/8/2r5/8/1k6/8/8/1K1Q4 w - - 0 1',
    you: 'w',
    goal: 'win',
    par: 30,
    note: 'Win the rook or mate. Zugzwang is the weapon: put the queen on the same rank/file/diagonal ' +
      'as the king and force the rook away from its king.'
  },
  {
    id: 'lucena',
    name: 'Lucena position — building the bridge',
    fen: '3K4/3P1k2/8/8/8/8/r7/4R3 w - - 0 1',
    you: 'w',
    goal: 'win',
    par: 10,
    note: 'The famous winning technique: rook to the fourth rank, march the king out, then shelter ' +
      'behind the rook.'
  },
  {
    id: 'philidor',
    name: 'Philidor position — the third-rank defense',
    fen: '8/4k3/r7/3KP3/8/8/8/7R b - - 0 1',
    you: 'b',
    goal: 'draw',
    par: 20,
    note: 'You are Black and you are drawing. Keep the rook on the sixth rank until the pawn advances, ' +
      'then drop behind it and check from the rear.'
  },
  {
    id: 'kp-k',
    name: 'King and pawn — the opposition',
    fen: '8/8/8/4k3/8/4K3/4P3/8 w - - 0 1',
    you: 'w',
    goal: 'win',
    par: 14,
    note: 'The king leads, the pawn follows. Take the opposition and promote.'
  },
  {
    id: 'rook-pawn-draw',
    name: 'Rook pawn + wrong bishop (draw)',
    fen: '7k/8/8/8/8/5B2/7P/7K b - - 0 1',
    you: 'b',
    goal: 'draw',
    par: 12,
    note: 'You are Black. The h-pawn plus a light-squared bishop cannot control h8 — sit in the corner and the game is drawn.'
  }
];
