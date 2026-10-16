#!/usr/bin/env python3
"""
Opening classifier + win/loss breakdown for a chess.com / lichess PGN export.

Writes parsed_results.json (one record per game, `idx` = position among the
user's games sorted oldest -> newest) and prints record tables by opening.
This script only counts results; it knows nothing about move quality. Run
engine_analysis.py before drawing conclusions about *why* openings score badly.

Usage:
    python analyze_openings.py --pgn games.pgn [--username NAME] [--last 50]

Needs python-chess (see setup_env.sh). First run downloads the free lichess
ECO opening database into --eco-dir.
"""
import argparse
import csv
import json
import os
import sys
import urllib.request
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import outcome, read_user_games, user_color  # noqa: E402

ECO_BASE_URL = "https://raw.githubusercontent.com/lichess-org/chess-openings/master/"
ECO_FILES = ["a.tsv", "b.tsv", "c.tsv", "d.tsv", "e.tsv"]


def ensure_eco_data(eco_dir):
    os.makedirs(eco_dir, exist_ok=True)
    for fname in ECO_FILES:
        path = os.path.join(eco_dir, fname)
        if not os.path.exists(path):
            print(f"Downloading {ECO_BASE_URL + fname} ...", file=sys.stderr)
            urllib.request.urlretrieve(ECO_BASE_URL + fname, path)
    return [os.path.join(eco_dir, f) for f in ECO_FILES]


def load_eco_database(paths):
    d = {}
    for path in paths:
        with open(path, encoding="utf-8") as fh:
            for row in csv.DictReader(fh, delimiter="\t"):
                d[row["pgn"].strip()] = (row["name"].strip(), row["eco"].strip())
    return d, sorted(d, key=len, reverse=True)


def moves_string(game):
    board = game.board()
    san = []
    for mv in game.mainline_moves():
        san.append(board.san(mv))
        board.push(mv)
    text = " ".join(f"{i // 2 + 1}. {m}" if i % 2 == 0 else m for i, m in enumerate(san))
    return text, san


def classify(text, d, keys):
    # whole-move match so "1. e4 e5 2. Nf3" never matches inside a longer token
    for k in keys:
        if text == k or text.startswith(k + " "):
            return d[k]
    return ("Unknown", "")


def family(name):
    return name.split(":")[0].strip()


def breakdown(rows, key_fn, min_games):
    stats = defaultdict(lambda: {"win": 0, "loss": 0, "draw": 0, "unknown": 0})
    for r in rows:
        stats[(key_fn(r), r["user_color"])][r["outcome"]] += 1
    out = []
    for (name, color), s in stats.items():
        n = sum(s.values())
        if n < min_games:
            continue
        out.append({"opening": name, "color": color, "games": n, "wins": s["win"],
                    "losses": s["loss"], "draws": s["draw"],
                    "win_rate": round(100 * s["win"] / n, 1),
                    "loss_rate": round(100 * s["loss"] / n, 1)})
    out.sort(key=lambda r: (-r["games"], -r["loss_rate"]))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pgn", required=True)
    ap.add_argument("--username", help="omit to auto-detect (the player in nearly every game)")
    ap.add_argument("--last", type=int, help="only the most recent N games")
    ap.add_argument("--eco-dir", default="eco_data")
    ap.add_argument("--min-games-family", type=int, default=3)
    ap.add_argument("--min-games-line", type=int, default=2)
    ap.add_argument("--json-out", default="parsed_results.json")
    args = ap.parse_args()

    username, games = read_user_games(args.pgn, args.username, args.last)
    d, keys = load_eco_database(ensure_eco_data(args.eco_dir))

    rows = []
    for idx, g in enumerate(games):
        h = g.headers
        text, san = moves_string(g)
        name, eco = classify(text, d, keys)
        color = user_color(g, username)
        rows.append({
            "idx": idx,
            "date": h.get("Date", ""), "end_time": h.get("EndTime", ""),
            "user_color": color,
            "opponent": h["Black"] if color == "White" else h["White"],
            "opening": name, "eco": eco, "outcome": outcome(g, username),
            "time_control": h.get("TimeControl", ""),
            "user_elo": int(h.get("WhiteElo" if color == "White" else "BlackElo", 0) or 0),
            "opp_elo": int(h.get("BlackElo" if color == "White" else "WhiteElo", 0) or 0),
            "plies": len(san),                 # half-moves; full moves = (plies + 1) // 2
            "full_moves": (len(san) + 1) // 2,
        })
    with open(args.json_out, "w") as f:
        json.dump({"username": username, "games": rows}, f, indent=2)

    print(f"Player: {username} | games analysed: {len(rows)} "
          f"({rows[0]['date']} to {rows[-1]['date']})")
    for title, fn, mn in (("By opening family", lambda r: family(r["opening"]), args.min_games_family),
                          ("By specific line", lambda r: r["opening"], args.min_games_line)):
        print(f"\n=== {title} (min {mn} games) ===")
        for r in breakdown(rows, fn, mn):
            print(f"{r['opening']} ({r['color']}): {r['games']} games | W{r['wins']}-L{r['losses']}-D{r['draws']} "
                  f"| win {r['win_rate']}% | loss {r['loss_rate']}%")
    w = sum(r["outcome"] == "win" for r in rows)
    l = sum(r["outcome"] == "loss" for r in rows)
    dr = sum(r["outcome"] == "draw" for r in rows)
    print(f"\nOverall: {len(rows)} games, W{w}-L{l}-D{dr}")
    for color in ("White", "Black"):
        sub = [r for r in rows if r["user_color"] == color]
        if sub:
            sw = sum(r["outcome"] == "win" for r in sub)
            sl = sum(r["outcome"] == "loss" for r in sub)
            sd = sum(r["outcome"] == "draw" for r in sub)
            print(f"As {color}: {len(sub)} games, W{sw}-L{sl}-D{sd}, win rate {100 * sw / len(sub):.0f}%")
    tcs = defaultdict(list)
    for r in rows:
        tcs[r["time_control"]].append(r)
    if len(tcs) > 1:
        print("\nBy time control (ratings differ between pools, so compare within a pool):")
        for tc, sub in sorted(tcs.items()):
            sw = sum(r["outcome"] == "win" for r in sub)
            sl = sum(r["outcome"] == "loss" for r in sub)
            sd = sum(r["outcome"] == "draw" for r in sub)
            print(f"  {tc}: {len(sub)} games, W{sw}-L{sl}-D{sd}")


if __name__ == "__main__":
    main()
