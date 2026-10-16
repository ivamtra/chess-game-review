#!/usr/bin/env bash
# Prepare python-chess and Stockfish, then print two lines to eval or copy:
#   CHESS_PY=/path/to/python
#   STOCKFISH=/path/to/stockfish
#
# Why a virtualenv: `pip install python-chess` into the system Python can fail
# with "AttributeError: install_layout" (old setuptools). A venv builds cleanly,
# so it is the fallback whenever `import chess` does not already work.
#
# Why GitHub for Stockfish: apt often has no stockfish package in sandboxes, but
# github.com is normally reachable and the official release is a single binary.
set -u
ROOT="${CHESS_SETUP_DIR:-${TMPDIR:-/tmp}/chess-analysis-env}"
STOCKFISH_VERSION="${STOCKFISH_VERSION:-sf_17.1}"
mkdir -p "$ROOT"

PY=python3
if ! "$PY" -c "import chess" 2>/dev/null; then
  if [ ! -x "$ROOT/venv/bin/python" ]; then
    python3 -m venv "$ROOT/venv" >&2 || { echo "ERROR: could not create a virtualenv" >&2; exit 1; }
  fi
  "$ROOT/venv/bin/pip" install -q python-chess >&2 || { echo "ERROR: pip install python-chess failed" >&2; exit 1; }
  PY="$ROOT/venv/bin/python"
fi

SF="${STOCKFISH:-}"
[ -z "$SF" ] && SF="$(command -v stockfish || true)"
[ -z "$SF" ] && [ -x /usr/games/stockfish ] && SF=/usr/games/stockfish
if [ -z "$SF" ]; then
  OS="$(uname -s)"; ARCH="$(uname -m)"
  if [ "$OS" = "Linux" ] && [ "$ARCH" = "x86_64" ]; then
    if grep -qw avx2 /proc/cpuinfo 2>/dev/null; then ASSET=stockfish-ubuntu-x86-64-avx2
    elif grep -qw sse4_1 /proc/cpuinfo 2>/dev/null; then ASSET=stockfish-ubuntu-x86-64-sse41-popcnt
    else ASSET=stockfish-ubuntu-x86-64; fi
  elif [ "$OS" = "Darwin" ] && [ "$ARCH" = "arm64" ]; then ASSET=stockfish-macos-m1-apple-silicon
  elif [ "$OS" = "Darwin" ]; then ASSET=stockfish-macos-x86-64-avx2
  else
    echo "ERROR: no prebuilt Stockfish known for $OS/$ARCH. Install stockfish and set STOCKFISH=/path." >&2
    exit 2
  fi
  URL="https://github.com/official-stockfish/Stockfish/releases/download/$STOCKFISH_VERSION/$ASSET.tar"
  echo "Downloading $URL" >&2
  curl -fsSL -o "$ROOT/sf.tar" "$URL" || { echo "ERROR: could not download Stockfish (is github.com reachable?)" >&2; exit 3; }
  tar -xf "$ROOT/sf.tar" -C "$ROOT" || { echo "ERROR: could not unpack Stockfish" >&2; exit 3; }
  SF="$ROOT/stockfish/$ASSET"
  chmod +x "$SF"
fi

# Smoke test: the engine must answer the UCI handshake.
if ! printf 'uci\nquit\n' | "$SF" 2>/dev/null | grep -q uciok; then
  echo "ERROR: $SF did not answer the UCI handshake" >&2
  exit 4
fi
echo "CHESS_PY=$PY"
echo "STOCKFISH=$SF"
