#!/usr/bin/env python3
"""
validate.py — sanity-check the lists/ + configs/ tree without rendering.

Phase 1.7.1. Designed to run in CI on every PR, before render.py, so a
malformed sources.yaml or a config referencing a non-existent list dir
fails fast rather than 60 s into a fetch.

Checks:

    1. Every configs/*.toml has a `name` and a non-empty `include[]`.
    2. Every entry in `include[]` resolves to a lists/<name>/ directory.
    3. Every lists/<level>/sources.yaml is valid YAML and has the
       expected keys per source: name, url, format, license, description.
    4. Every URL is HTTPS (HTTP is rejected — supply-chain hygiene).
    5. Every additions.txt and exemptions.txt parses cleanly via the
       same normaliser the renderer uses (so additions can't ship
       silently-dropped malformed lines).

Exit codes:

    0  all checks passed
    1  at least one error (printed to stderr)
"""

from __future__ import annotations

import sys
from pathlib import Path

import tomllib  # py3.11+
import yaml

# Reuse the renderer's normaliser so additions.txt entries that the
# renderer would silently drop also fail validation.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from render import normalise_domain, LISTS_DIR, CONFIGS_DIR  # noqa: E402

REQUIRED_SOURCE_KEYS = {"name", "url", "format", "license", "description"}
ALLOWED_FORMATS = {"hosts", "domains", "abp"}

errors: list[str] = []


def check_configs() -> None:
    if not CONFIGS_DIR.is_dir():
        errors.append(f"{CONFIGS_DIR} missing")
        return
    configs = sorted(CONFIGS_DIR.glob("*.toml"))
    if not configs:
        errors.append(f"no tier configs in {CONFIGS_DIR}")
        return
    for cfg in configs:
        try:
            with cfg.open("rb") as fh:
                spec = tomllib.load(fh)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{cfg}: TOML parse error: {exc}")
            continue
        if not spec.get("name"):
            errors.append(f"{cfg}: missing 'name'")
        includes = spec.get("include") or []
        if not includes:
            errors.append(f"{cfg}: include[] must not be empty")
        for level in includes:
            level_dir = LISTS_DIR / level
            if not level_dir.is_dir():
                errors.append(f"{cfg}: includes '{level}' but {level_dir} does not exist")


def check_sources() -> None:
    for level_dir in sorted(LISTS_DIR.iterdir()):
        if not level_dir.is_dir():
            continue
        sources_yaml = level_dir / "sources.yaml"
        if not sources_yaml.exists():
            errors.append(f"{level_dir}: missing sources.yaml")
            continue
        try:
            with sources_yaml.open() as fh:
                spec = yaml.safe_load(fh) or {}
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{sources_yaml}: YAML parse error: {exc}")
            continue
        sources = spec.get("sources")
        if sources is None:
            errors.append(f"{sources_yaml}: missing 'sources' key")
            continue
        for src in sources:
            if not isinstance(src, dict):
                errors.append(f"{sources_yaml}: source entry is not a mapping")
                continue
            missing = REQUIRED_SOURCE_KEYS - set(src.keys())
            if missing:
                errors.append(f"{sources_yaml}: source missing keys {sorted(missing)}: {src!r}")
                continue
            url = src["url"]
            if not isinstance(url, str) or not url.startswith("https://"):
                errors.append(f"{sources_yaml}: source {src['name']!r} URL is not HTTPS: {url!r}")
            fmt = src["format"]
            if fmt not in ALLOWED_FORMATS:
                errors.append(f"{sources_yaml}: source {src['name']!r} format {fmt!r} not in {sorted(ALLOWED_FORMATS)}")


def check_addexempt() -> None:
    for level_dir in sorted(LISTS_DIR.iterdir()):
        if not level_dir.is_dir():
            continue
        for fname in ("additions.txt", "exemptions.txt"):
            path = level_dir / fname
            if not path.exists():
                continue
            for lineno, raw in enumerate(path.read_text().splitlines(), 1):
                stripped = raw.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                if normalise_domain(stripped) is None:
                    errors.append(f"{path}:{lineno}: malformed entry {stripped!r}")


def main() -> int:
    check_configs()
    check_sources()
    check_addexempt()
    if errors:
        print(f"\n[validate] {len(errors)} error(s):\n", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1
    print("[validate] OK", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
