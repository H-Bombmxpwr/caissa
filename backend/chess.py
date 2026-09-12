"""Standard chess rules, 0x88 board, legal SAN and canonical position keys.

No runtime dependencies; used only for library indexing, never for UI latency.
"""
import hashlib
import re

START = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1'
OFFSETS = {'n': (-33, -31, -18, -14, 14, 18, 31, 33),
           'b': (-17, -15, 15, 17), 'r': (-16, -1, 1, 16),
           'q': (-17, -16, -15, -1, 1, 15, 16, 17),
           'k': (-17, -16, -15, -1, 1, 15, 16, 17)}

def square(name):
    return (8 - int(name[1])) * 16 + ord(name[0]) - 97

def name(sq):
    return chr(97 + (sq & 7)) + str(8 - (sq >> 4))

def color(piece):
    return 'w' if piece.isupper() else 'b'

class Chess:
    def __init__(self, fen=START):
        fields = fen.split()
        if len(fields) != 6:
            raise ValueError('FEN needs six fields')
        self.board = [''] * 128
        rows = fields[0].split('/')
        if len(rows) != 8:
            raise ValueError('FEN needs eight ranks')
        for r, row in enumerate(rows):
            f = 0
            for p in row:
                if p.isdigit():
                    f += int(p)
                elif p in 'pnbrqkPNBRQK' and f < 8:
                    self.board[r * 16 + f] = p
                    f += 1
                else:
                    raise ValueError('Invalid FEN placement')
            if f != 8:
                raise ValueError('Invalid FEN rank')
        self.turn, self.castling = fields[1:3]
        self.ep = square(fields[3]) if fields[3] != '-' else None
        self.half, self.full = map(int, fields[4:])
        if self.turn not in ('w', 'b'):
            raise ValueError('Invalid FEN turn')

    def fen(self):
        rows = []
        for r in range(8):
            row, empty = '', 0
            for f in range(8):
                p = self.board[r * 16 + f]
                if not p:
                    empty += 1
                else:
                    row += (str(empty) if empty else '') + p
                    empty = 0
            rows.append(row + (str(empty) if empty else ''))
        return ' '.join(['/'.join(rows), self.turn, self.castling or '-',
                         name(self.ep) if self.ep is not None else '-', str(self.half), str(self.full)])

    def attacked(self, target, by):
        for src in range(128):
            if src & 0x88:
                continue
            p = self.board[src]
            if not p or color(p) != by:
                continue
            kind = p.lower()
            offsets = ((-17, -15) if by == 'w' else (15, 17)) if kind == 'p' else OFFSETS[kind]
            for step in offsets:
                dst = src + step
                while not dst & 0x88:
                    if dst == target:
                        return True
                    if self.board[dst] or kind in 'pnk':
                        break
                    dst += step
        return False

    def check(self, side=None):
        side = side or self.turn
        king = 'K' if side == 'w' else 'k'
        try:
            sq = self.board.index(king)
        except ValueError:
            return True
        return self.attacked(sq, 'b' if side == 'w' else 'w')

    def pseudo(self):
        result = []
        for src in range(128):
            if src & 0x88:
                continue
            p = self.board[src]
            if not p or color(p) != self.turn:
                continue
            kind = p.lower()
            if kind == 'p':
                step = -16 if self.turn == 'w' else 16
                targets = []
                dst = src + step
                if not dst & 0x88 and not self.board[dst]:
                    targets.append(dst)
                    if src >> 4 == (6 if self.turn == 'w' else 1) and not self.board[dst + step]:
                        targets.append(dst + step)
                for dst in (src + step - 1, src + step + 1):
                    if not dst & 0x88 and ((self.board[dst] and color(self.board[dst]) != self.turn) or
                        (dst == self.ep and self.board[dst - step] == ('p' if self.turn == 'w' else 'P'))):
                        targets.append(dst)
                for dst in targets:
                    for promotion in ('qrbn' if dst >> 4 in (0, 7) else ['']):
                        result.append((src, dst, promotion))
                continue
            for step in OFFSETS[kind]:
                dst = src + step
                while not dst & 0x88:
                    other = self.board[dst]
                    if other and color(other) == self.turn:
                        break
                    result.append((src, dst, ''))
                    if other or kind in 'nk':
                        break
                    dst += step
            if kind == 'k' and src == (116 if self.turn == 'w' else 4) and not self.check():
                enemy = 'b' if self.turn == 'w' else 'w'
                for right, delta, rook, between in [('K', 2, 3, [1, 2]), ('Q', -2, -4, [-1, -2, -3])]:
                    if self.turn == 'b':
                        right = right.lower()
                    if right in self.castling and self.board[src + rook] == ('R' if self.turn == 'w' else 'r'):
                        if all(not self.board[src + d] for d in between) and all(
                            not self.attacked(src + d, enemy) for d in [delta // 2, delta]):
                            result.append((src, src + delta, ''))
        return result

    def push(self, move):
        src, dst, promotion = move
        p, capture = self.board[src], self.board[dst]
        old_ep = self.ep
        self.ep = None
        if p.lower() == 'p':
            if dst == old_ep and not capture and (src & 7) != (dst & 7):
                self.board[dst + (16 if self.turn == 'w' else -16)] = ''
            if abs(dst - src) == 32:
                self.ep = (src + dst) // 2
        if p.lower() == 'k':
            for right in ('KQ' if self.turn == 'w' else 'kq'):
                self.castling = self.castling.replace(right, '')
            if abs(dst - src) == 2:
                rook_src, rook_dst = (src + 3, src + 1) if dst > src else (src - 4, src - 1)
                self.board[rook_dst], self.board[rook_src] = self.board[rook_src], ''
        for sq, right in [(0, 'q'), (7, 'k'), (112, 'Q'), (119, 'K')]:
            if sq in (src, dst):
                self.castling = self.castling.replace(right, '')
        self.board[src] = ''
        self.board[dst] = (promotion.upper() if self.turn == 'w' else promotion) if promotion else p
        self.half = 0 if capture or p.lower() == 'p' else self.half + 1
        self.full += self.turn == 'b'
        self.turn = 'b' if self.turn == 'w' else 'w'

    def snapshot(self):
        return self.board[:], self.turn, self.castling, self.ep, self.half, self.full

    def restore(self, state):
        self.board, self.turn, self.castling, self.ep, self.half, self.full = state

    def legal(self):
        result = []
        for move in self.pseudo():
            state = self.snapshot()
            side = self.turn
            self.push(move)
            if not self.check(side):
                result.append(move)
            self.restore(state)
        return result

    def san(self, move, legal=None):
        src, dst, promo = move
        p = self.board[src].lower()
        if p == 'k' and abs(dst - src) == 2:
            text = 'O-O' if dst > src else 'O-O-O'
        else:
            capture = bool(self.board[dst]) or (p == 'p' and dst == self.ep)
            text = '' if p == 'p' else p.upper()
            others = [m for m in (legal if legal is not None else self.legal())
                      if m[0] != src and m[1] == dst and self.board[m[0]].lower() == p]
            if p == 'p' and capture:
                text += name(src)[0]
            elif others:
                same_file = any(m[0] & 7 == src & 7 for m in others)
                same_rank = any(m[0] >> 4 == src >> 4 for m in others)
                text += name(src) if same_file and same_rank else name(src)[1 if same_file else 0]
            text += ('x' if capture else '') + name(dst) + ('=' + promo.upper() if promo else '')
        state = self.snapshot()
        self.push(move)
        if self.check():
            text += '+' if self.legal() else '#'
        self.restore(state)
        return text

    def move(self, text):
        clean = re.sub(r'[+#?!]', '', text).replace('0', 'O').replace('=', '')
        legal = self.legal()
        for move in legal:
            uci = name(move[0]) + name(move[1]) + move[2]
            san = self.san(move, legal)
            if clean in (uci, re.sub(r'[+#]', '', san).replace('=', '')):
                self.push(move)
                return san
        raise ValueError('Illegal or ambiguous move: ' + text)

    def key(self):
        fields = self.fen().split()[:4]
        if self.ep is not None and not any(self.board[m[0]].lower() == 'p' and m[1] == self.ep
                                         for m in self.legal()):
            fields[3] = '-'
        return hashlib.sha256(' '.join(fields).encode()).hexdigest()[:32]

    def perft(self, depth):
        if depth == 0:
            return 1
        count = 0
        for move in self.legal():
            state = self.snapshot()
            self.push(move)
            count += self.perft(depth - 1)
            self.restore(state)
        return count
