# Chess game review skill

A Claude skill that reviews a chess.com / lichess PGN export with opening statistics and Stockfish, then
produces a report document with Lichess links to the key mistakes.

It answers: where am I losing points, in which phase of the game, which openings actually hurt me, and
which positions did I throw away?

## Layout

```
chess-opening-analysis/
  SKILL.md                  skill instructions (workflow, report structure, interpretation rules)
  scripts/
    setup_env.sh            python-chess in a venv + official Stockfish binary
    analyze_openings.py     ECO opening classification and results tables
    engine_analysis.py      Stockfish pass: per-move evals, turning points, depth re-checks
    summarize.py            merges both into report_data.md (+ optional annotated PGN)
    common.py               shared helpers
```

## Running the scripts by hand

```bash
eval "$(bash chess-opening-analysis/scripts/setup_env.sh | sed 's/^/export /')"
"$CHESS_PY" chess-opening-analysis/scripts/analyze_openings.py --pgn games.pgn --last 50
"$CHESS_PY" chess-opening-analysis/scripts/engine_analysis.py --pgn games.pgn --engine "$STOCKFISH" --last 50
"$CHESS_PY" chess-opening-analysis/scripts/summarize.py --pgn games.pgn --last 50 --pgn-out annotated.pgn
```

`report_data.md` then holds every table, and `annotated.pgn` can be imported at lichess.org/paste.

## Notes

- Engine results are deterministic for a given depth: the hash table is cleared per game.
- Stockfish is downloaded from the official GitHub releases and is not bundled here
  (it is GPL-licensed; see https://github.com/official-stockfish/Stockfish).
- The opening names come from the lichess `chess-openings` database, downloaded on first run.
