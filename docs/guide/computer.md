# Play the computer

Choose **Play computer** in the sidebar. Select White, Black, or Random and a level
from 1 to 11, then choose **New game**. You can move pieces or enter a move in SAN.
Promotion offers a choice of queen, rook, bishop, or knight.

Stockfish runs locally in a separate process from analysis. Levels 1–11 map to
Stockfish Skill Level 0–20 in steps of two, with 175–925 ms per move. These are
practice settings, not Elo ratings. Level 11 goes to eleven; it uses full skill
within that time budget.

**Take back** undoes your last move and the computer reply. **Resign** ends the game.
Checkmate, stalemate, insufficient material, the fifty-move rule and repeated
positions end play automatically. The board remains available when visiting other
sections during the session; reloading the app starts a fresh session.

**Analyze game** opens a separate analysis tab. **Save to database** saves the current
PGN snapshot in **Computer games**. Saving later positions produces another snapshot;
identical snapshots are deduplicated by the importer. Save before starting another
game or closing the app if you want to keep it.
