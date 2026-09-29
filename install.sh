#!/usr/bin/env bash
# Install the "airship-engagement-review" skill globally for the current user by
# symlinking it into ~/.cursor/skills/ so it is available across ALL your projects.
#
# Usage:
#   ./install.sh            # create/refresh the symlink
#   ./install.sh --copy     # copy instead of symlink (no live updates from this repo)
#   ./install.sh --uninstall
#
# (You can also just open this repo as your Cursor workspace — the skill auto-loads
#  from .cursor/skills/ without installing anything.)
set -euo pipefail

SKILL="airship-engagement-review"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$REPO_DIR/.cursor/skills/$SKILL"
DEST_DIR="$HOME/.cursor/skills"
DEST="$DEST_DIR/$SKILL"

if [[ ! -d "$SRC" ]]; then
  echo "error: skill not found at $SRC" >&2
  exit 1
fi

mkdir -p "$DEST_DIR"

case "${1:-}" in
  --uninstall)
    if [[ -L "$DEST" || -e "$DEST" ]]; then
      rm -rf "$DEST"
      echo "removed $DEST"
    else
      echo "nothing to remove at $DEST"
    fi
    exit 0
    ;;
  --copy)
    rm -rf "$DEST"
    cp -R "$SRC" "$DEST"
    echo "copied skill -> $DEST"
    ;;
  "")
    rm -rf "$DEST"
    ln -s "$SRC" "$DEST"
    echo "linked $DEST -> $SRC"
    ;;
  *)
    echo "unknown option: $1" >&2
    exit 1
    ;;
esac

echo "Done. Restart Cursor (or reload) so it picks up ~/.cursor/skills/$SKILL."
