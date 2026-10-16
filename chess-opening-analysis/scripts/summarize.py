#!/usr/bin/env python3
"""
Merge parsed_results.json (openings) with engine_results.json (Stockfish) and write
report_data.md: every table the report needs, with links to the key positions.
Also prints consistency checks so numbers in the report can be trusted.

Usage:
    python summarize.py [--parsed parsed_results.json] [--engine engine_results.json]
                        [--out report_data.md] [--pgn games.pgn --pgn-out annotated.pgn --last 50]

--pgn-out is optional: an annotated PGN of the lost games (marks + best-move variations)
that can be imported into lichess.org/paste.
"""
import argparse
import json
import os
import statistics as st
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import MISTAKE, BLUNDER, INACCURACY, fmt_eval  # noqa: E402

GIVEBACK_EVAL = 200  # centipawns: "clearly winning" = +2.0 or better for the user


def family(name):
    return name.split(":")[0].strip()


def clamp(cp, lim=1000):
    return max(-lim, min(lim, cp))


def record(rows):
    w = sum(r["outcome"] == "win" for r in rows)
    l = sum(r["outcome"] == "loss" for r in rows)
    d = sum(r["outcome"] == "draw" for r in rows)
    return w, l, d


def rec_str(rows):
    w, l, d = record(rows)
    n = len(rows)
    return f"{n} games, W{w}-L{l}-D{d} ({100 * w / n:.0f}% wins)" if n else "0 games"


def eval_at_move10(g):
    ev = g["user_evals"]
    return ev[min(20, len(ev) - 1)]


def opening_table(games, key_fn, min_games):
    groups = defaultdict(list)
    for g in games:
        groups[(key_fn(g), g["user_color"])].append(g)
    rows = []
    for (name, color), gs in groups.items():
        if len(gs) < min_games:
            continue
        w, l, d = record(gs)
        ev10 = [clamp(eval_at_move10(g)) for g in gs]
        avg10 = st.mean(ev10) / 100
        good = 100 * sum(e >= 50 for e in ev10) / len(gs)
        opening_errs = sum(1 for g in gs for m in g["moves"]
                           if m["user"] and m["phase"] == "opening" and m["win_drop"] >= MISTAKE)
        verdict = ("opening problem" if avg10 <= -0.5
                   else "fine position out of the opening" if avg10 >= 0.3 else "about equal")
        if len(gs) < 5:
            verdict += " (small sample)"
        rows.append((name, color, len(gs), w, l, d, 100 * w / len(gs), avg10, good, opening_errs, verdict))
    rows.sort(key=lambda r: (-r[2], r[6]))
    return rows


def md_table(header, rows):
    out = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def tp_cells(g):
    tp = g["turning_point"]
    if not tp:
        return ["-", "-", "-", "-"]
    move = f"{tp['move_no']}{'...' if g['user_color'] == 'Black' else '.'}{tp['san']}"
    swing = f"{fmt_eval(tp['cp_before'])} -> {fmt_eval(tp['cp_after'])}"
    return [move, tp["best"] or "-", swing, tp.get("punish") or "-"]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--parsed", default="parsed_results.json")
    ap.add_argument("--engine", default="engine_results.json")
    ap.add_argument("--out", default="report_data.md")
    ap.add_argument("--min-games-family", type=int, default=3)
    ap.add_argument("--min-games-line", type=int, default=3)
    ap.add_argument("--pgn")
    ap.add_argument("--pgn-out")
    ap.add_argument("--last", type=int)
    args = ap.parse_args()

    parsed = json.load(open(args.parsed))
    eng = json.load(open(args.engine))
    user = parsed["username"]
    by_idx = {g["idx"]: g for g in parsed["games"]}
    games = []
    for e in eng["games"]:
        g = dict(by_idx[e["idx"]])
        g.update(e)
        games.append(g)
    n = len(games)

    # ---- consistency checks -------------------------------------------------
    assert len(parsed["games"]) == n, "parsed/engine game counts differ - rerun both with the same --last/--username"
    for g in games:
        assert g["outcome"] == by_idx[g["idx"]]["outcome"]
    w, l, d = record(games)
    assert w + l + d == n, "unknown results present"
    assert sum(len([x for x in games if x["user_color"] == c]) for c in ("White", "Black")) == n
    print(f"CHECKS OK: {n} games, W{w}-L{l}-D{d}")

    L = []  # report_data.md lines
    add = L.append
    add(f"# Game review data for {user}\n")
    add(f"Games: {n} ({games[0]['date']} to {games[-1]['date']}). Engine: Stockfish, depth {eng['depth']} "
        f"(turning points of lost/thrown-away games re-checked at depth {eng['recheck_depth']}). "
        f"Game numbers (#) are chronological within this set.\n")

    # ---- record -------------------------------------------------------------
    add("## Record\n")
    add(f"- Overall: {rec_str(games)}")
    for c in ("White", "Black"):
        add(f"- As {c}: {rec_str([g for g in games if g['user_color'] == c])}")
    tcs = defaultdict(list)
    for g in games:
        tcs[g["time_control"]].append(g)
    if len(tcs) > 1:
        for tc, gs in sorted(tcs.items(), key=lambda kv: -len(kv[1])):
            avg = st.mean(x["user_elo"] for x in gs)
            add(f"- Time control {tc}: {rec_str(gs)}; average rating in that pool {avg:.0f}")
        add("  (Rating pools differ per time control, so do not read rating changes across pools as progress.)")
    hi = [g for g in games if g["opp_elo"] > g["user_elo"]]
    lo = [g for g in games if g["opp_elo"] <= g["user_elo"]]
    add(f"- Against higher-rated opponents: {rec_str(hi)}")
    add(f"- Against equal/lower-rated opponents: {rec_str(lo)}\n")

    # ---- openings -----------------------------------------------------------
    hdr = ["Opening", "Color", "Games", "W-L-D", "Win %", "Avg eval at move 10", "% games >= +0.5 at move 10",
           "Serious errors in opening phase", "Verdict on the opening itself"]
    for title, fn, mn in (("Openings by family", lambda g: family(g["opening"]), args.min_games_family),
                          ("Openings by specific line", lambda g: g["opening"], args.min_games_line)):
        add(f"## {title} (min {mn} games)\n")
        rows = [(a, b, c, f"{dw}-{dl}-{dd}", f"{wr:.0f}", f"{a10:+.1f}", f"{gd:.0f}", oe, v)
                for a, b, c, dw, dl, dd, wr, a10, gd, oe, v in opening_table(games, fn, mn)]
        add(md_table(hdr, rows) + "\n")
    add("Read the last column before recommending any repertoire change: an opening only needs "
        "replacing when the engine says the position out of it is worse, not when it merely has a low win rate.\n")

    # ---- mistakes by phase --------------------------------------------------
    add("## Where the mistakes happen\n")
    nm, serious, blund = Counter(), Counter(), Counter()
    for g in games:
        for m in g["moves"]:
            if m["user"]:
                nm[m["phase"]] += 1
                if m["win_drop"] >= MISTAKE:
                    serious[m["phase"]] += 1
                if m["win_drop"] >= BLUNDER:
                    blund[m["phase"]] += 1
    rows = [(p, nm[p], serious[p], blund[p], f"{100 * serious[p] / max(nm[p], 1):.1f}")
            for p in ("opening", "middlegame", "endgame")]
    add(md_table(["Phase", "Your moves", "Mistakes + blunders", "of which blunders", "Per 100 moves"], rows))
    add("\nPhases: opening = first 10 moves; endgame = little material left (knights, bishops, rooks, queens "
        "worth 24 points or less in total); middlegame = the rest. Mistake = a move costing 20+ win-probability "
        "points, blunder = 30+.\n")
    rows = []
    for o in ("win", "loss", "draw"):
        gs = [g for g in games if g["outcome"] == o]
        if not gs:
            continue
        um = [m for g in gs for m in g["moves"] if m["user"]]
        rows.append((o, len(gs), f"{sum(m['win_drop'] >= BLUNDER for m in um) / len(gs):.2f}",
                     f"{sum(MISTAKE <= m['win_drop'] < BLUNDER for m in um) / len(gs):.2f}",
                     f"{sum(max(m['win_drop'], 0) for m in um) / len(um):.1f}"))
    add(md_table(["Result", "Games", "Blunders per game", "Mistakes per game", "Avg win-prob % lost per move"], rows))
    add("")

    # ---- thrown-away advantages ----------------------------------------------
    add("## Winning positions thrown away\n")
    give = [g for g in games if g["outcome"] != "win" and g["peak_eval"] >= GIVEBACK_EVAL]
    losses = [g for g in games if g["outcome"] == "loss"]
    gl = [g for g in give if g["outcome"] == "loss"]
    add(f"{len(give)} games were not won even though you reached +2.0 or better "
        f"({len(gl)} of your {len(losses)} losses, {len(give) - len(gl)} draws).\n")
    rows = []
    for g in sorted(give, key=lambda x: -x["peak_eval"]):
        c = tp_cells(g)
        tp = g["turning_point"]
        rows.append((f"#{g['idx'] + 1}", g["date"], g["opponent"], g["outcome"], fmt_eval(g["peak_eval"]),
                     *c, tp["phase"] if tp else "-", f"[board]({tp['link']})" if tp else "-"))
    add(md_table(["Game", "Date", "Opponent", "Result", "Peak eval", "Your move", "Better", "Eval swing",
                  "Punished by", "Phase", "Position"], rows) + "\n")
    if gl:
        tps = [g["turning_point"] for g in gl if g["turning_point"]]
        add(f"Turning-point moves in these losses: median move number {st.median(t['move_no'] for t in tps):.0f}; "
            f"phases {dict(Counter(t['phase'] for t in tps))}; "
            f"{sum(('x' in t['san'] or '+' in t['san']) for t in tps)} of {len(tps)} were captures or checks.\n")

    # ---- all losses ---------------------------------------------------------
    add("## All losses with the move that decided them\n")
    rows = []
    for g in losses:
        tp = g["turning_point"]
        c = tp_cells(g)
        rows.append((f"#{g['idx'] + 1}", g["date"], g["opponent"], g["user_color"], f"{g['user_elo']}v{g['opp_elo']}",
                     fmt_eval(g["peak_eval"]), *c, tp["phase"] if tp else "-",
                     f"[board]({tp['link']})" if tp else "-"))
    add(md_table(["Game", "Date", "Opponent", "Color", "Ratings", "Peak eval", "Your move", "Better",
                  "Eval swing", "Punished by", "Phase", "Position"], rows) + "\n")
    add("Describe a mistake only as far as the engine data supports: the played move, the better move, the eval "
        "swing and the punishing reply are verified; any story about why (king safety, a pin, time trouble) is "
        "a guess unless you checked the position.\n")

    # ---- long games / time --------------------------------------------------
    long_losses = [g for g in losses if g["full_moves"] >= 50]
    add("## Other signals\n")
    add(f"- Losses lasting 50+ moves: {len(long_losses)} of {len(losses)}; losses ending before move 30: "
        f"{sum(g['full_moves'] < 30 for g in losses)} of {len(losses)}.\n")

    with open(args.out, "w") as f:
        f.write("\n".join(L) + "\n")
    json.dump({"username": user, "games": n, "record": [w, l, d],
               "giveback_games": [g["idx"] + 1 for g in give]}, open("summary.json", "w"))
    print(f"Wrote {args.out}")

    # ---- optional annotated PGN --------------------------------------------
    if args.pgn_out:
        if not args.pgn:
            sys.exit("--pgn-out needs --pgn (and the same --last used for the analysis)")
        import chess
        import chess.pgn
        from common import read_user_games
        _, src = read_user_games(args.pgn, user, args.last)
        wanted = {g["idx"]: g for g in losses}
        with open(args.pgn_out, "w") as out:
            for idx, g in wanted.items():
                orig = src[idx]
                new = chess.pgn.Game()
                new.headers = orig.headers.copy()
                new.headers["Annotator"] = f"Stockfish depth {eng['depth']}"
                node, b = new, orig.board()
                for ply, mv in enumerate(orig.mainline_moves()):
                    rec = g["moves"][ply]
                    parent = node
                    node = node.add_main_variation(mv)
                    if rec["user"] and rec["win_drop"] >= INACCURACY and rec["best"]:
                        d_ = rec["win_drop"]
                        node.nags.add(chess.pgn.NAG_BLUNDER if d_ >= BLUNDER else
                                      chess.pgn.NAG_MISTAKE if d_ >= MISTAKE else chess.pgn.NAG_DUBIOUS_MOVE)
                        node.comment = (f"Your eval {fmt_eval(rec['cp_before'])} -> {fmt_eval(rec['cp_after'])}. "
                                        f"Better: {rec['best']}")
                        try:
                            parent.add_variation(b.parse_san(rec["best"])).comment = "Engine best"
                        except ValueError:
                            pass
                    b.push(mv)
                # a fresh exporter per game: reusing one makes every game repeat all the earlier ones
                out.write(new.accept(chess.pgn.StringExporter(headers=True, variations=True, comments=True)) + "\n\n")
        print(f"Wrote {args.pgn_out} ({len(wanted)} lost games)")


if __name__ == "__main__":
    main()
