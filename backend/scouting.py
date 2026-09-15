"""Player evidence from mainline PGNs. No inferred evaluations or population claims."""
import hashlib
import json
import math
import re
import time
from collections import defaultdict

from . import openings as opening_names
from . import pgnutil
from .chess import Chess, START, color

VERSION = 3
SCHEMA = '''
CREATE TABLE IF NOT EXISTS scouting_cache (
 game_id INTEGER PRIMARY KEY REFERENCES games(id) ON DELETE CASCADE,
 digest TEXT NOT NULL, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS scouting_drills (
 id INTEGER PRIMARY KEY, player TEXT NOT NULL,
 game_id INTEGER NOT NULL REFERENCES games(id) ON DELETE CASCADE,
 digest TEXT NOT NULL, ply INTEGER NOT NULL, fen TEXT NOT NULL, theme TEXT NOT NULL,
 solution TEXT NOT NULL, due INTEGER NOT NULL, interval INTEGER NOT NULL DEFAULT 0,
 attempts INTEGER NOT NULL DEFAULT 0, successes INTEGER NOT NULL DEFAULT 0,
 UNIQUE(player,game_id,digest,ply));
'''


def annotations(text):
    """Nodes include the root; comments after a move belong to its resulting position."""
    nodes = [dict(san=None, cp=None, clock=None)]
    depth = 0
    for token in pgnutil.TOKEN_RE.finditer(pgnutil.movetext(text)):
        if token.group(2):
            depth += 1
        elif token.group(3):
            depth = max(0, depth - 1)
        elif depth:
            continue
        elif token.group(7) and len(token.group(7)) > 1:
            nodes.append(dict(san=token.group(7), cp=None, clock=None))
        elif token.group(1):
            comment = token.group(1)
            ev = re.search(r'\[%eval\s+(-?\d+(?:\.\d+)?)(?:\s*[,\]])', comment)
            clk = re.search(r'\[%clk\s+(\d+):(\d{2}):(\d{2}(?:\.\d+)?)\]', comment)
            if ev:
                nodes[-1]['cp'] = round(float(ev[1]) * 100)
            if clk and int(clk[2]) < 60 and float(clk[3]) < 60:
                nodes[-1]['clock'] = int(clk[1]) * 3600 + int(clk[2]) * 60 + float(clk[3])
    return nodes


def features(board, side):
    own = [p.lower() for p in board.board if p and color(p) == side]
    enemy = 'b' if side == 'w' else 'w'
    all_pieces = ''.join(board.board).lower()
    nonpawns = sum(all_pieces.count(p) for p in 'nbrq')
    phase = 'endgame' if nonpawns <= 4 and 'q' not in all_pieces else ('opening' if board.full <= 12 else 'middlegame')
    tags = [phase]
    for who, label in ((side, 'Own'), (enemy, 'Opposing')):
        files = [sq & 7 for sq, p in enumerate(board.board) if p and p.lower() == 'p' and color(p) == who]
        if 3 in files and 2 not in files and 4 not in files:
            tags.append(label + ' isolated d-pawn')
        if len(files) > len(set(files)):
            tags.append(label + ' doubled pawns')
    if 'r' in own and all_pieces.count('r') >= 2 and not any(p in all_pieces for p in 'nbq'):
        tags.append('Rook ending')
    values = {'p': 1, 'n': 3, 'b': 3, 'r': 5, 'q': 9, 'k': 0}
    balance = sum(values[p.lower()] * (1 if color(p) == side else -1) for p in board.board if p)
    if balance >= 3:
        tags.append('Material advantage')
    elif balance <= -3:
        tags.append('Material deficit')
    return phase, tags


def tally(scores):
    scores = [s for s in scores if s is not None]
    n = len(scores)
    mean = sum(scores) / n if n else None
    # Hoeffding interval handles draws as bounded half-points, not Bernoulli wins.
    radius = math.sqrt(math.log(40) / (2 * n)) if n else None
    return dict(games=n, score_pct=round(mean * 100, 1) if n else None,
                interval_pct=[round(max(0, mean-radius)*100, 1), round(min(1, mean+radius)*100, 1)] if n else None)


class Scouting:
    def __init__(self, library):
        self.library = library
        library.connect().executescript(SCHEMA)

    def extract(self, row):
        text = self.library.game_pgn(row['id']) or ''
        digest = hashlib.sha256((str(VERSION) + text).encode()).hexdigest()
        db = self.library.connect()
        cached = db.execute('SELECT data FROM scouting_cache WHERE game_id=? AND digest=?', (row['id'], digest)).fetchone()
        if cached:
            return digest, json.loads(cached[0])
        tags = pgnutil.headers(text)
        if tags.get('Variant', 'Standard').lower() not in ('standard', 'chess', ''):
            raise ValueError('Unsupported variant')
        board = Chess(tags.get('FEN') or START)
        nodes = annotations(text)
        tc = re.fullmatch(r'(\d+)(?:\+(\d+))?', tags.get('TimeControl', ''))
        clocks = {'w': float(tc[1]), 'b': float(tc[1])} if tc and board.fen() == START else {}
        increment = float(tc[2] or 0) if tc else None
        result = []
        line = []
        for ply, node in enumerate(nodes[1:]):
            side = board.turn
            phase, themes = features(board, side)
            before, after = nodes[ply]['cp'], node['cp']
            loss = max(0, (before-after) * (1 if side == 'w' else -1)) if before is not None and after is not None else None
            clock = node['clock']
            spent = clocks[side] + increment - clock if clock is not None and side in clocks and increment is not None else None
            if spent is not None and spent < 0:
                spent = None
            clocks.pop(side, None)
            if clock is not None:
                clocks[side] = clock
            line.append(node['san'])
            result.append(dict(ply=ply, move=board.full, side=side, fen=board.fen(), key=board.key(), san=node['san'],
                               phase=phase, themes=themes, loss=loss, cp=before, clock=clock, spent=spent,
                               line=' '.join(line) if ply < 24 else None))
            board.move(node['san'])
            result[-1]['next_key'] = board.key()
            result[-1]['fen_after'] = board.fen()
        with self.library._write_lock, db:
            db.execute('INSERT OR REPLACE INTO scouting_cache VALUES(?,?,?)', (row['id'], digest, json.dumps(result)))
        return digest, result

    def report(self, query):
        player = str(query.get('player', '')).strip()
        if not player:
            raise ValueError('Enter the exact player name or handle used in the PGN')
        minimum = max(2, min(100, int(query.get('min_games', 5))))
        clauses = ['(lower(g.white)=lower(?) OR lower(g.black)=lower(?))']
        params = [player, player]
        if query.get('collection'):
            clauses.append('(g.collection_id=? OR g.id IN (SELECT game_id FROM game_collections WHERE collection_id=?))')
            params += [int(query['collection'])] * 2
        for key, column, op in [('speed', 'speed', '='), ('since', 'date', '>='), ('until', 'date', '<=')]:
            if query.get(key):
                clauses.append('g.' + column + op + '?')
                params.append(str(query[key]).replace('-', '.') if column == 'date' else query[key])
        rows = self.library.connect().execute('SELECT g.* FROM games g WHERE ' + ' AND '.join(clauses) + ' ORDER BY g.date DESC,g.id DESC', params).fetchall()
        scores, groups, openings = [], defaultdict(dict), defaultdict(dict)
        opening_lines = {}
        named = defaultdict(dict)
        named_meta = {}
        completed_by_side = defaultdict(int)
        losses, clocks, mistakes, skipped = defaultdict(list), [], [], []
        games_with_eval = set()
        clock_games = set()
        catalogue = {}
        for row in rows:
            side = 'w' if row['white'].casefold() == player.casefold() else 'b'
            if query.get('color') in ('w', 'b') and side != query['color']:
                continue
            try:
                digest, moves = self.extract(row)
            except (ValueError, TypeError) as err:
                skipped.append(dict(game_id=row['id'], reason=str(err)))
                continue
            outcome = row['result']
            score = .5 if outcome == '1/2-1/2' else (float(outcome == ('1-0' if side == 'w' else '0-1')) if outcome in ('1-0', '0-1') else None)
            scores.append(score)
            if score is not None:
                completed_by_side[side] += 1
            catalogue[row['id']] = dict(id=row['id'], white=row['white'], black=row['black'], date=row['date'],
                                        result=outcome, speed=row['speed'], event=row['event'], color=side,
                                        opponent=row['black'] if side == 'w' else row['white'],
                                        opponent_elo=row['black_elo'] if side == 'w' else row['white_elo'],
                                        eco=row['eco'], opening=row['opening'])
            # The opening as the library names it. A game that never got a name is
            # classified here from its own first moves rather than left uncounted.
            title = row['opening'] or None
            eco = row['eco'] or None
            if not title:
                guess = opening_names.classify((row['first_moves'] or '').split())
                if guess:
                    title, eco = guess['opening'], eco or guess['eco']
            if title:
                named[(side, title)][row['id']] = score
                named_meta.setdefault((side, title), dict(eco=eco, moves=(row['first_moves'] or '').split()[:12]))
            seen = set()
            for move in moves:
                if move['side'] != side:
                    continue
                for theme in move['themes']:
                    if theme not in seen:
                        groups[theme][row['id']] = score
                        seen.add(theme)
                if move['line'] and move['ply'] in (6, 7, 14, 15, 22, 23):
                    openings[(side, move['next_key'])][row['id']] = score
                    opening_lines.setdefault((side, move['next_key']),
                                             dict(line=move['line'], moves=move['line'].split(),
                                                  fen=move.get('fen_after'), ply=move['ply'] + 1))
                loss = move['loss']
                if loss is not None:
                    games_with_eval.add(row['id'])
                    losses[move['phase']].append(loss)
                    losses['After move 30' if move['move'] > 30 else 'Through move 30'].append(loss)
                    if 'Rook ending' in move['themes'] and move['cp'] is not None and move['cp'] * (1 if side == 'w' else -1) >= 200:
                        groups['Winning rook ending (at least +2 pawns)'][row['id']] = score
                    if loss >= 150:
                        mistakes.append(dict(game_id=row['id'], digest=digest, color=side, **move))
                if move['clock'] is not None:
                    clock_games.add(row['id'])
                    clocks.append(dict(game_id=row['id'], color=side, **move))
        baseline = tally(scores)
        patterns = [dict(theme=theme, **tally(list(values.values())), evidence=list(values)[:12]) for theme, values in groups.items()]
        for item in patterns:
            item['small_sample'] = item['games'] < minimum
            item['difference_pp'] = round(item['score_pct'] - baseline['score_pct'], 1) if item['games'] and baseline['games'] else None
        patterns.sort(key=lambda x: (x['small_sample'], x['difference_pp'] if x['difference_pp'] is not None else 100))
        repertoire = [dict(color=side, key=key, **opening_lines[(side, key)], **tally(list(values.values())), evidence=list(values)[:12])
                      for (side, key), values in openings.items()]
        for entry in repertoire:
            denominator = completed_by_side[entry['color']]
            entry['frequency_pct'] = round(100 * entry['games']/denominator, 1) if denominator else None
            found = opening_names.classify(entry['moves'])
            entry['name'] = found['opening'] if found else None
            entry['eco'] = found['eco'] if found else None
        repertoire.sort(key=lambda x: -x['games'])
        # What they open with, by name rather than by position. Position lines transpose
        # and split; the name is the thing a reader recognises and can prepare against.
        catalogued = [dict(color=side, opening=title, evidence=list(values)[:12],
                           **named_meta[(side, title)], **tally(list(values.values())))
                      for (side, title), values in named.items()]
        for entry in catalogued:
            denominator = completed_by_side[entry['color']]
            entry['frequency_pct'] = round(100 * entry['games']/denominator, 1) if denominator else None
        catalogued.sort(key=lambda x: (-x['games'], x['opening']))
        weak = sorted([r for r in repertoire if r['games'] >= minimum], key=lambda r: (r['score_pct'], -r['games']))[:10]
        timed = [m for m in clocks if m['spent'] is not None]
        repertoire, catalogued = repertoire[:40], catalogued[:40]
        mistakes = sorted(mistakes, key=lambda m: -m['loss'])[:100]
        thinks = sorted(timed, key=lambda m: -m['spent'])[:10]
        # Only the games something in the report actually points at travel with it: the
        # scan may have read thousands, and the reader can only follow the ones on screen.
        cited = {i for group in (patterns, repertoire, catalogued, weak) for entry in group for i in entry['evidence']}
        cited.update(m['game_id'] for m in mistakes)
        cited.update(m['game_id'] for m in thinks)
        catalogue = {i: catalogue[i] for i in cited if i in catalogue}
        return dict(player=player, baseline=baseline, analyzed_games=len(scores), skipped=skipped,
                    evaluated_games=len(games_with_eval), clock_games=len(clock_games), minimum_games=minimum,
                    patterns=patterns, repertoire=repertoire, weakest_lines=weak, openings=catalogued,
                    games=catalogue, collection=int(query['collection']) if query.get('collection') else None,
                    suggested_line=weak[0] if weak else None,
                    accuracy=[dict(phase=k, moves=len(v), mean_cp_loss=round(sum(v)/len(v), 1)) for k, v in losses.items()],
                    clocks=dict(moves=len(clocks), low_time_moves=sum(m['clock'] < 30 for m in clocks),
                                measured_thinks=len(timed), longest_thinks=thinks),
                    mistakes=mistakes,
                    notes=['Scores count wins as 1 and draws as 0.5; unfinished games are excluded.',
                           'Intervals are conservative 95% bounds assuming independent games. Patterns are descriptive, not causal.',
                           'Evaluations require adjacent saved [%eval] annotations; mate scores are excluded.',
                           'Clock time uses consecutive same-player clocks and simple base+increment controls.',
                           'Opening names come from the lichess CC0 opening index, applied to the moves actually played.',
                           'No population benchmark, theory departure or tactical motif is inferred.'])

    def drills(self, player):
        return [dict(r) for r in self.library.connect().execute('SELECT id,game_id,ply,fen,theme,due,interval,attempts,successes FROM scouting_drills WHERE player=? ORDER BY due,id', (player.strip().casefold(),))]

    def human_moves(self, query):
        board = Chess(query.get('fen') or START)
        low, high = int(query.get('min_elo', 1400)), int(query.get('max_elo', 1800))
        if not 0 <= low <= high <= 4000:
            raise ValueError('Use a rating range between 0 and 4000')
        column = 'white_elo' if board.turn == 'w' else 'black_elo'
        rows = self.library.connect().execute('''SELECT p.game_id,p.next_san,g.result FROM positions p
            JOIN games g ON g.id=p.game_id WHERE p.hash=? AND p.next_san IS NOT NULL
            AND g.''' + column + ''' BETWEEN ? AND ? ORDER BY p.game_id,p.ply''', (board.key(),low,high)).fetchall()
        seen, groups = set(), defaultdict(list)
        for row in rows:
            if row['game_id'] in seen:
                continue
            seen.add(row['game_id'])
            result = row['result']
            score = .5 if result == '1/2-1/2' else (float(result == '1-0') if result in ('1-0','0-1') else None)
            groups[row['next_san']].append(score)
        return dict(games=len(seen), min_elo=low, max_elo=high,
                    moves=sorted([dict(san=san, observations=len(scores), frequency_pct=round(100*len(scores)/len(seen),1),
                                       white_score=tally(scores)) for san,scores in groups.items()], key=lambda m:-m['observations']),
                    note='Observed moves in your indexed library, filtered by mover rating. First occurrence per game. This is not a Maia prediction or a representative population sample.')

    def create_drill(self, body, engine):
        player = str(body.get('player', '')).strip()
        row = self.library.connect().execute('SELECT * FROM games WHERE id=?', (int(body['game_id']),)).fetchone()
        if not player or not row or player.casefold() not in (row['white'].casefold(), row['black'].casefold()):
            raise ValueError('Choose a game played by this player')
        side = 'w' if row['white'].casefold() == player.casefold() else 'b'
        digest, moves = self.extract(row)
        move = next((m for m in moves if m['ply'] == int(body['ply']) and m['side'] == side and m['loss'] is not None and m['loss'] >= 150), None)
        mistake = dict(game_id=row['id'], digest=digest, **move) if move else None
        if not mistake:
            raise ValueError('This position is no longer a recorded mistake for this player')
        out = engine.analyze(mistake['fen'], movetime=800, multipv=1)
        solution = out.get('bestmove')
        if not solution or solution == '0000':
            raise ValueError('The engine did not return a solution')
        Chess(mistake['fen']).move(solution)
        with self.library._write_lock, self.library.connect() as db:
            db.execute('INSERT OR IGNORE INTO scouting_drills(player,game_id,digest,ply,fen,theme,solution,due) VALUES(?,?,?,?,?,?,?,?)',
                       (player.casefold(), mistake['game_id'], mistake['digest'], mistake['ply'], mistake['fen'], mistake['phase'], solution, int(time.time())))
        return dict(drills=self.drills(player))

    def review(self, ident, body):
        with self.library._write_lock, self.library.connect() as db:
            row = db.execute('SELECT * FROM scouting_drills WHERE id=?', (int(ident),)).fetchone()
            if not row:
                raise ValueError('Practice position not found')
            now = int(time.time())
            if row['due'] > now:
                raise ValueError('This position is not due for a retest yet')
            board = Chess(row['fen'])
            answer = board.move(str(body.get('move', '')).strip())
            correct = answer == Chess(row['fen']).move(row['solution'])
            interval = min(30, max(1, row['interval'] * 3)) if correct else 1
            due = now + interval * 86400
            db.execute('UPDATE scouting_drills SET attempts=attempts+1, successes=successes+?, interval=?, due=? WHERE id=?', (int(correct), interval, due, row['id']))
        return dict(correct=correct, solution=Chess(row['fen']).move(row['solution']), due=due,
                    message='Retest scheduled; practice success does not yet prove improvement in games.')
