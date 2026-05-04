#!/usr/bin/env python3
"""
release_notes.py — emit per-tier summary lines from dist/manifest.json
                   for the GitHub Actions release workflow.

Reads dist/manifest.json (produced by render.py earlier in the same
workflow run), prints one bullet per tier to stdout. Stderr is reserved
for warnings; the workflow captures stdout into the release body.

Kept as a standalone script (rather than inlined in release.yml) because
embedding Python f-strings inside a YAML heredoc is brittle: backslashes,
quote escaping, and indentation rules clash badly between bash, YAML,
and Python's own parser. Doing the formatting in a real .py file moves
the problem to a place where it can be unit-tested in isolation.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    manifest = Path("dist/manifest.json")
    if not manifest.exists():
        print(f"release_notes.py: {manifest} missing", file=sys.stderr)
        return 1
    m = json.loads(manifest.read_text())
    for lvl in m.get("levels", []):
        name = lvl["name"]
        count = lvl["domain_count"]
        sha = lvl["sha256"][:12]
        srcs = ", ".join(lvl["source_levels"])
        print(f"- **{name}** \u2014 {count} domains, sha256 `{sha}\u2026`, sources: {srcs}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
