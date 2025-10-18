#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ "$#" -ge 1 ] && [[ "$1" != --* ]]; then
  MATCH_ID="$1"
  shift
  uv run python "$SCRIPT_DIR/visualizer/match_viewer.py" --match-id "$MATCH_ID" "$@"
else
  uv run python "$SCRIPT_DIR/visualizer/match_viewer.py" "$@"
fi
