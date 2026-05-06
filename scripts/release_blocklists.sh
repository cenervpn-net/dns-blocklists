#!/usr/bin/env bash
set -euo pipefail

# release_blocklists.sh
#
# Safe operator wrapper for blocklist releases:
#   1) validates sources/config
#   2) renders tagged artifacts
#   3) (optional) creates and pushes git tag
#
# Example:
#   ./scripts/release_blocklists.sh --tag v1.0.2 --push

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd -P)"

TAG=""
DO_PUSH=0
ASSUME_YES=0

usage() {
  cat <<'EOF'
Usage: scripts/release_blocklists.sh --tag <tag> [--push] [--yes]

Required:
  --tag <tag>   Release tag (v1.2.3 or v2026.05.06)

Options:
  --push        Create annotated git tag and push to origin
  --yes         Skip interactive confirmation before push

Notes:
  - Script requires clean git state before release.
  - Without --push, this runs validation/render only (dry-run release prep).
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --tag)
      TAG="${2:-}"
      shift 2
      ;;
    --push)
      DO_PUSH=1
      shift
      ;;
    --yes)
      ASSUME_YES=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if [[ -z "$TAG" ]]; then
  echo "--tag is required" >&2
  usage >&2
  exit 1
fi

if [[ ! "$TAG" =~ ^v([0-9]+\.[0-9]+\.[0-9]+|[0-9]{4}\.[0-9]{2}\.[0-9]{2})$ ]]; then
  echo "Invalid tag format: $TAG" >&2
  echo "Expected v1.2.3 or v2026.05.06" >&2
  exit 1
fi

cd "$REPO_ROOT"

if [[ ! -d .git ]]; then
  echo "Not a git repository: $REPO_ROOT" >&2
  exit 1
fi

branch="$(git rev-parse --abbrev-ref HEAD)"
if [[ "$branch" != "main" ]]; then
  echo "Refusing release from branch '$branch'. Switch to 'main' first." >&2
  exit 1
fi

if [[ -n "$(git status --porcelain)" ]]; then
  echo "Working tree is not clean. Commit/stash changes before release." >&2
  git status --short
  exit 1
fi

if git rev-parse "$TAG" >/dev/null 2>&1; then
  echo "Tag already exists locally: $TAG" >&2
  exit 1
fi

if git ls-remote --exit-code --tags origin "refs/tags/$TAG" >/dev/null 2>&1; then
  echo "Tag already exists on origin: $TAG" >&2
  exit 1
fi

echo "[release] validate"
python3 scripts/validate.py

echo "[release] render for tag $TAG"
python3 scripts/render.py --tag "$TAG"

if [[ ! -s dist/manifest.json ]]; then
  echo "dist/manifest.json missing after render" >&2
  exit 1
fi

echo "[release] manifest summary"
python3 scripts/release_notes.py

if [[ "$DO_PUSH" -eq 0 ]]; then
  echo
  echo "[release] dry-run complete (no tag pushed)."
  echo "Run with --push to publish this release tag."
  exit 0
fi

if [[ "$ASSUME_YES" -eq 0 ]]; then
  echo
  read -r -p "Create and push tag '$TAG' to origin now? [y/N] " answer
  case "$answer" in
    y|Y|yes|YES) ;;
    *)
      echo "Aborted before push."
      exit 1
      ;;
  esac
fi

git tag -a "$TAG" -m "DNS blocklist release $TAG"
git push origin "$TAG"

echo
echo "[release] tag pushed: $TAG"
echo "Next:"
echo "  1) In admin DNS page, click 'Poll now'"
echo "  2) Force sync canary gateway"
echo "  3) Verify loaded_tag=$TAG, then roll out fleet"
