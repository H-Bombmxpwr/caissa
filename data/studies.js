/* Studies and visualization puzzles for level 6.
 * `line` is the main solution; `alts` are other defenses and how to meet them. */
window.STUDIES = [
  {
    id: 'reti',
    name: 'Réti — the king that catches everything (1921)',
    fen: '7K/8/k1P5/7p/8/8/8/8 w - - 0 1',
    you: 'w',
    goal: 'draw',
    difficulty: 'famous',
    line: '1. Kg7 h4 2. Kf6 h3 (2... Kb6 3. Ke5 h3 4. Kd6) 3. Ke7 h2 4. c7 Kb7 5. Kd7',
    idea: 'The white king appears hopelessly far from the h-pawn. It walks a diagonal that ' +
      'chases the pawn and supports c6-c7 at the same time.'
  },
  {
    id: 'saavedra',
    name: 'Saavedra position (1895)',
    fen: '8/8/1KP5/3r4/8/8/8/k7 w - - 0 1',
    you: 'w',
    goal: 'win',
    difficulty: 'famous',
    line: '1. c7 Rd6+ 2. Kb5 Rd5+ 3. Kb4 Rd4+ 4. Kb3 Rd3+ 5. Kc2 Rd4 6. c8=R Ra4 7. Kb3',
    idea: 'Promoting to a queen is only a draw (…Rd4+! and stalemate after Qxd4). The underpromotion ' +
      'to a rook threatens mate and wins.'
  },
  {
    id: 'lucena-study',
    name: 'Lucena — build the bridge',
    fen: '3K4/3P1k2/8/8/8/8/r7/4R3 w - - 0 1',
    you: 'w',
    goal: 'win',
    difficulty: 'technique',
    line: '1. Re4 Ra1 2. Kc7 Rc1+ 3. Kb6 Rb1+ 4. Kc6 Rc1+ 5. Kb5 Rb1+ 6. Rb4',
    idea: 'The rook on the fourth rank is the bridge the king hides behind.'
  },
  {
    id: 'anastasia',
    name: "Anastasia's mate",
    fen: '5b1k/pp2N1pp/8/8/7Q/8/PPP3K1/4R3 w - - 0 1',
    you: 'w',
    goal: 'mate',
    difficulty: 'pattern',
    line: '1. Qxh7+ Kxh7 2. Rh1#',
    idea: 'The knight on e7 owns g8 and g6 and the bishop blocks f8, so the queen can drag the king ' +
      'onto the open h-file, where the rook mates.'
  },
  {
    id: 'backrank',
    name: 'Back rank — mate in one',
    fen: '6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1',
    you: 'w',
    goal: 'mate',
    difficulty: 'easy',
    line: '1. Ra8#',
    idea: 'Warm-up: hold the whole back rank in your head — where can the king actually go?'
  },
  {
    id: 'smothered',
    name: "Philidor's legacy (smothered mate)",
    fen: '5r1k/6pp/8/6N1/8/1Q6/8/6K1 w - - 0 1',
    you: 'w',
    goal: 'mate',
    difficulty: 'pattern',
    line: '1. Nf7+ Kg8 2. Nh6+ Kh8 3. Qg8+ Rxg8 4. Nf7#',
    idea: 'Nh6 is a double check, so the king must move; his own rook on f8 seals the escape and the ' +
      'queen sacrifices herself to smother him.'
  }
];
