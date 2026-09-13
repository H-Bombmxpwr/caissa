# Blindfold training

The seven-level visualisation trainer is a module inside the app. It runs on the same
board renderer as the analysis view, so the pieces, palette and animation settings you
chose apply here too.

## Peeking

Hold `Space`, or the **Peek** button, to reveal the board. Peeks are counted and shown
with your result, because a session with thirty peeks and a session with none are not the
same session.

Peeking reveals the *position* and never a computed answer. If an exercise is asking for a
square colour or a knight path, peeking shows you the board, not the solution.

## The two blindfold styles

As on lichess:

- **Hide the pieces** — the board and its coordinates stay, the pieces do not. Good for
  training piece tracking while keeping your bearings.
- **Hide the board entirely** — nothing but the move list. Good for calculation.

## Drilling a repertoire blindfold

Repertoire drills use the same blindfold board by default, with the same peek control. It
is the most direct way to find out whether you know a line or merely recognise it.


Switching training chapters clears the previous board before the next exercise mounts.
In Square colors, **Continue / Enter** advances after a miss without requiring a
keyboard. The shared **Peek** button reveals the position using your hold/flash setting.
