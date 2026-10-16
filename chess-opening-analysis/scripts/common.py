"""Shared helpers for the chess game review scripts."""
import collections
import math
import sys

import chess
import chess.pgn

# Thresholds in "win probability points" lost by one move (lichess convention).
INACCURACY, MISTAKE, BLUNDER = 10, 20, 30

PIECE_VALUE = {chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9}


def win_prob(cp):
    """Win probability (0-100) for the side whose centipawn score is `cp`."""
    return 50 + 50 * (2 / (1 + math.exp(-0.00368208 * cp)) - 1)


def is_mate(cp):
    return abs(cp) >= 9000


def fmt_eval(cp):
    """Format a centipawn score from the user's point of view, e.g. +1.4 or 'mate'."""
    if is_mate(cp):
        return "mate for you" if cp > 0 else "mated"
    return f"{cp / 100:+.1f}"


def material(board):
    """Total knight/bishop/rook/queen value on the board, both sides (pawns ignored)."""
    return sum(PIECE_VALUE[p.piece_type] for p in board.piece_map().values()
               if p.piece_type in PIECE_VALUE)


def phase(board, ply):
    """opening = first 10 full moves; endgame = little material left; else middlegame."""
    if ply < 20:
        return "opening"
    if material(board) <= 24:
        return "endgame"
    return "middlegame"


def classify_drop(drop):
    if drop >= BLUNDER:
        return "blunder"
    if drop >= MISTAKE:
        return "mistake"
    if drop >= INACCURACY:
        return "inaccuracy"
    return None


def detect_username(games):
    """The player who appears in (almost) every game is the user."""
    names = collections.Counter()
    for g in games:
        for key in ("White", "Black"):
            names[g.headers.get(key, "")] += 1
    (name, n), = names.most_common(1)
    if n < 0.6 * len(games):
        top = ", ".join(f"{k} ({v})" for k, v in names.most_common(3))
        sys.exit(f"Could not tell which player is the user (most frequent: {top}). "
                 f"Ask the user for their username and pass --username.")
    return name


def read_user_games(pgn_path, username=None, last=None):
    """Return (username, games) with games sorted oldest -> newest.

    `last` keeps only the most recent N games (by Date + EndTime, so it works
    whether the export is oldest-first or newest-first). The position of a game
    in the returned list is its `idx` everywhere else.
    """
    games = []
    with open(pgn_path, encoding="utf-8") as fh:
        while True:
            g = chess.pgn.read_game(fh)
            if g is None:
                break
            games.append(g)
    if not games:
        sys.exit(f"No games found in {pgn_path}")
    if username is None:
        username = detect_username(games)
    u = username.lower()
    mine = [g for g in games
            if g.headers.get("White", "").lower() == u or g.headers.get("Black", "").lower() == u]
    if not mine:
        sys.exit(f"No games found for '{username}'. Check the White/Black tags in the PGN.")
    mine.sort(key=lambda g: (g.headers.get("Date", ""), g.headers.get("EndTime", "")))
    if last:
        mine = mine[-last:]
    # use the casing from the file
    first = mine[0].headers
    username = first["White"] if first.get("White", "").lower() == u else first["Black"]
    return username, mine


def user_color(game, username):
    return "White" if game.headers.get("White", "").lower() == username.lower() else "Black"


def outcome(game, username):
    r = game.headers.get("Result", "")
    color = user_color(game, username)
    if r == "1/2-1/2":
        return "draw"
    if r == "1-0":
        return "win" if color == "White" else "loss"
    if r == "0-1":
        return "win" if color == "Black" else "loss"
    return "unknown"


def lichess_link(fen, color):
    """Analysis-board link for a position, oriented from the user's side."""
    return f"https://lichess.org/analysis/{fen.replace(' ', '_')}?color={color.lower()}"
