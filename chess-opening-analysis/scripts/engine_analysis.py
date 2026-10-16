#!/usr/bin/env python3
"""
Stockfish pass over the user's games.

For every game: evaluates every position, grades each of the user's moves by the
win probability it cost, records the biggest swing ("turning point") and, for
lost games and games where the user was clearly winning, re-checks that turning
point at a deeper search and records the move that punished it.

Usage:
    python engine_analysis.py --pgn games.pgn --engine /path/to/stockfish \
        [--username NAME] [--last 50] [--depth 14] [--recheck-depth 20] [--workers N]

Writes engine_results.json. 50 games at depth 14 take a couple of minutes on 2 cores.
"""
import argparse
import io
import json
import multiprocessing as mp
import os
import sys

import chess
import chess.engine
import chess.pgn

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (MISTAKE, lichess_link, outcome, phase, read_user_games,  # noqa: E402
                    user_color, win_prob)

_engine = None
_cfg = {}


def _init(engine_path, depth, recheck_depth):
    global _engine
    _cfg.update(depth=depth, recheck=recheck_depth)
    _engine = chess.engine.SimpleEngine.popen_uci(engine_path)
    _engine.configure({"Threads": 1, "Hash": 128})


def _score(info, board_turn_pov=None):
    return info["score"].white().score(mate_score=10000)


def analyze_game(job):
    idx, pgn_text, username = job
    game = chess.pgn.read_game(io.StringIO(pgn_text))
    color = user_color(game, username)
    white = color == "White"
    upov = 1 if white else -1
    moves = list(game.mainline_moves())
    lim = chess.engine.Limit(depth=_cfg["depth"])
    # game=idx makes python-chess send `ucinewgame`, which clears Stockfish's hash table, so a
    # game's evaluations do not depend on which games the worker happened to analyse before it.

    # 1. evaluate every position once (white's point of view, centipawns)
    evals, bests = [], []
    b = game.board()
    for ply in range(len(moves) + 1):
        if b.is_game_over():
            evals.append((-10000 if b.turn == chess.WHITE else 10000) if b.is_checkmate() else 0)
            bests.append(None)
        else:
            info = _engine.analyse(b, lim, game=idx)
            evals.append(_score(info))
            bests.append(info["pv"][0] if info.get("pv") else None)
        if ply < len(moves):
            b.push(moves[ply])

    # 2. grade moves
    recs = []
    b = game.board()
    for ply, mv in enumerate(moves):
        mover_white = ply % 2 == 0
        pov = 1 if mover_white else -1
        before, after = evals[ply] * pov, evals[ply + 1] * pov
        recs.append({
            "ply": ply, "move_no": ply // 2 + 1, "san": b.san(mv),
            "best": b.san(bests[ply]) if bests[ply] else None,
            "user": mover_white == white, "phase": phase(b, ply),
            "cp_before": before, "cp_after": after,
            "win_drop": round(win_prob(before) - win_prob(after), 1),
        })
        b.push(mv)

    res = outcome(game, username)
    user_evals = [e * upov for e in evals]
    peak = max(user_evals)
    user_moves = [r for r in recs if r["user"]]

    # 3. turning point: first user move that cost >= MISTAKE, else the single worst move
    tp = None
    if user_moves:
        cand = next((r for r in user_moves if r["win_drop"] >= MISTAKE), None) \
               or max(user_moves, key=lambda r: r["win_drop"])
        tp = dict(cand)
        needs_recheck = res == "loss" or (res != "win" and peak >= 200)
        board = game.board()
        for m in moves[:cand["ply"]]:
            board.push(m)
        tp["fen_before"] = board.fen()
        if needs_recheck:
            deep = chess.engine.Limit(depth=_cfg["recheck"])
            i0 = _engine.analyse(board, deep, game=idx)
            tp["best"] = board.san(i0["pv"][0])
            tp["cp_before"] = i0["score"].pov(board.turn).score(mate_score=10000)
            board.push(moves[cand["ply"]])
            i1 = _engine.analyse(board, deep, game=idx)
            tp["cp_after"] = i1["score"].pov(not board.turn).score(mate_score=10000)
            tp["punish"] = board.san(i1["pv"][0]) if i1.get("pv") else None
            tp["rechecked_depth"] = _cfg["recheck"]
        tp["link"] = lichess_link(tp["fen_before"], color)

    return {"idx": idx, "outcome": res, "user_color": color, "peak_eval": peak,
            "user_evals": user_evals, "moves": recs, "turning_point": tp}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pgn", required=True)
    ap.add_argument("--engine", required=True, help="path to the stockfish binary")
    ap.add_argument("--username")
    ap.add_argument("--last", type=int)
    ap.add_argument("--depth", type=int, default=14)
    ap.add_argument("--recheck-depth", type=int, default=20)
    ap.add_argument("--workers", type=int, default=os.cpu_count() or 1)
    ap.add_argument("--out", default="engine_results.json")
    args = ap.parse_args()

    username, games = read_user_games(args.pgn, args.username, args.last)
    jobs = []
    for idx, g in enumerate(games):
        exp = chess.pgn.StringExporter(headers=True, variations=False, comments=False)
        jobs.append((idx, g.accept(exp), username))

    print(f"Analysing {len(jobs)} games for {username} at depth {args.depth} "
          f"with {args.workers} worker(s)...", file=sys.stderr)
    with mp.Pool(args.workers, initializer=_init,
                 initargs=(args.engine, args.depth, args.recheck_depth)) as pool:
        results = []
        for i, r in enumerate(pool.imap_unordered(analyze_game, jobs), 1):
            results.append(r)
            print(f"  {i}/{len(jobs)} done", file=sys.stderr, flush=True)
    results.sort(key=lambda r: r["idx"])
    with open(args.out, "w") as f:
        json.dump({"username": username, "depth": args.depth,
                   "recheck_depth": args.recheck_depth, "games": results}, f)
    print(f"Wrote {args.out} ({len(results)} games)")


if __name__ == "__main__":
    main()
