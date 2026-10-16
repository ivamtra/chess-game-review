---
name: chess-opening-analysis
description: Reviews a player's chess games from a chess.com or lichess PGN export with opening statistics AND Stockfish engine analysis, and produces a report document with Lichess links to the key mistakes. Use whenever the user uploads a chess PGN, mentions a chess.com game archive/export, or asks things like "analyze my chess games", "analyze my last 50 games", "where am I failing", "what should I study", "which openings do I struggle against", "why do I keep losing", "what's my win rate by opening", "do I blunder", or "when do I throw away winning positions" — even if they never say "Stockfish" or "skill". Also use it for follow-ups on an earlier analysis (re-slicing by color, opening or time control; going deeper on lost games). If the user only gives a username or profile URL, tell them how to export a PGN first (this skill needs the file, not live API access).
---

# Chess game review (openings + Stockfish)

Takes a list of games (a PGN file) and answers "where am I failing and what should I study?" with evidence from the engine, not just win/loss counts.

**Why the engine is not optional.** Win rates only say *that* a line scored badly, not *why*. In the case that motivated this skill, the opening table pointed at one line as the biggest leak, but Stockfish showed the player was +4 to +6 out of that line and then lost the advantage in the middlegame. Advice built on the table alone would have sent them to fix the wrong thing. Always run the engine before explaining causes or recommending repertoire changes.

## Inputs

- A PGN export (chess.com: `https://www.chess.com/games/archive/<username>` → pick dates → Download; lichess: export from the profile). Attached files live under `/mnt/user-data/uploads/`.
- Optional: a username (auto-detected as the player who appears in nearly every game), and "last N games" (`--last N`; works whether the file is oldest-first or newest-first).

If the user asks for N games and the file has fewer, analyse what is there and say so.

## Output

The deliverable is **a report document** containing the tables in `report_data.md`, plus **Lichess board links** to the key mistake positions (already inside those tables). The chat reply is only one or two sentences (the headline finding and a pointer to the report). Offer the annotated PGN (`--pgn-out`) or a chart only if the user wants them; they are not part of the default output.

## Workflow

Work in a scratch directory, never inside the skill folder or the uploads folder. Run Python with `-I` when it reads user files.

1. **Open the report first (if Claude Docs tools are available).** Follow the docs skill: create the doc skeleton (title, headings) before the slow steps so the user sees it fill in. If no Docs tools exist, build a .docx with the docx skill instead.
2. **Set up tools:** `bash <skill>/scripts/setup_env.sh` prints `CHESS_PY=` and `STOCKFISH=`. It creates a virtualenv for python-chess (system `pip install python-chess` can fail with `install_layout` errors) and downloads the official Stockfish binary from GitHub. If it fails, say exactly why and fall back to opening statistics only, stating clearly that the "why" could not be checked, and do not give cause-based advice.
3. **Opening statistics:** `$CHESS_PY -I scripts/analyze_openings.py --pgn <file> [--last N]` → `parsed_results.json`.
4. **Engine pass:** `$CHESS_PY -I scripts/engine_analysis.py --pgn <file> --engine $STOCKFISH [--last N]` → `engine_results.json`. 50 games take about 1.5 minutes on 2 cores at depth 14; every lost game and every thrown-away win is re-checked at depth 20. Use the same `--last`/`--username` in every script, because game numbers must line up.
5. **Report tables:** `$CHESS_PY -I scripts/summarize.py [--pgn <file> --last N --pgn-out annotated.pgn]` → `report_data.md` and "CHECKS OK". Fix any failed check before writing anything.
6. **Write the report** from `report_data.md` (structure below), then reply in chat.

## Report structure

1. **Headline**: the single biggest finding in two or three sentences.
2. **Record**: overall, by color, by time control, vs higher- vs lower-rated opponents.
3. **Openings** (family and line tables with the engine "verdict on the opening itself").
4. **Where the mistakes happen**: opening / middlegame / endgame rates per 100 moves; blunders per game in wins vs losses.
5. **Winning positions thrown away**: the games that were +2.0 or better and not won, with played move, better move, eval swing, the punishing reply and a board link. Say which move numbers and phases the swings cluster in.
6. **All losses** with the move that decided each one and its board link.
7. **Prioritized study plan** (see below).
8. **Method**: engine and depth, phase definitions, mistake thresholds, and that engine numbers are approximate.

## Reading the data correctly

- **Opening verdict comes from the engine, not the win rate.** Only call something an opening problem when the average eval at move 10 is negative (the table says "opening problem") or the deciding move falls in the opening phase. A low win rate with a fine eval out of the opening means the games were lost later; recommend a different opening only in the first case.
- **Count with the right unit.** `plies` are half-moves; `full_moves` are what players call "moves". Phases: opening = first 10 moves, endgame = 24 points or less of knights/bishops/rooks/queens on the board, middlegame = the rest.
- **Compare ratings within a time control.** Rating pools differ (for example about 1500 in 5-minute games and 1630 in 10-minute games), so a jump between sessions is the pool, not progress.
- **Small samples:** under 5 games per opening is a hint, not a finding; say so.
- **Describe mistakes only as far as the data goes.** Played move, better move, eval swing and punishing reply are verified. Stories such as "exposed king" or "walked into a pin" are guesses unless you looked at the position; label them or leave them out. Mate shows as "mated" or "mate for you", never as a number like -100.
- **Results are deterministic** (the engine hash is cleared per game), so rerunning on the same file reproduces the numbers. Different depths will shift them slightly.

## Turning findings into a study plan

Order the plan by how much win probability each leak costs, using the report's own numbers:

- Many thrown-away wins or blunders in the middlegame → a per-move blunder check (what can the opponent capture, check or threaten after my move?), tactics puzzles aimed at hanging pieces and mate threats, and conversion technique (trade pieces when ahead, compare candidate captures instead of playing the first one). Note when the better move was itself a capture or check: the fix is comparing options, not avoiding captures.
- Opening verdict "opening problem" for a line with enough games → a specific repertoire fix for that line only.
- Long losses or a loss on time → endgame practice and clock handling; cite how many games.
- Keep the plan to three to five items, each tied to a number from the report. Offer to walk through any lost game, and name the first two or three board links to start with (the biggest swings).

## Options

- `--min-games-family`, `--min-games-line` change the table cut-offs; `--depth`, `--recheck-depth` change search strength; `--workers` sets parallelism.
- `engine_results.json` keeps per-move evals for every game, so follow-up questions (by color, opening, time control, phase) can be answered from it without rerunning the engine.
