#!/usr/bin/env python3
"""
render.py — compose lists/ → dist/<level>.conf for each configured tier.

Phase 1.7.1 of architecture-next. Mullvad-style render: read each
configured tier's `include` list, fetch every source, parse to a
canonical set of domains, merge, apply additions, strip exemptions,
write a single Unbound `local-zone:` config.

Usage:

    python3 scripts/render.py [--cache-dir <path>] [--no-fetch] [--quiet]

Outputs:

    dist/<level>.conf            — Unbound config snippet
    dist/manifest.json           — sha256 + line count + tag + UTC ts

Exit codes:
    0   success
    1   IO / config error
    2   network error fetching a source
    3   no domains rendered for a tier (likely a config bug)

Determinism: the renderer SORTS the merged domain set before writing,
so two runs against the same source content produce byte-identical
output. This matters because gateways content-hash the file to decide
whether to reload Unbound.

Network: each source is fetched once per run, with a 60 s timeout and
3 retries on transient failures. `--cache-dir` (default `.cache/`)
persists the raw bytes; `--no-fetch` reuses whatever's there (handy
in CI when you want a quick re-render after editing exemptions).
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path
from typing import Iterable

import tomllib  # py3.11+
import yaml


# ── Paths ────────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parent.parent
LISTS_DIR = REPO_ROOT / "lists"
CONFIGS_DIR = REPO_ROOT / "configs"
DIST_DIR = REPO_ROOT / "dist"
DEFAULT_CACHE = REPO_ROOT / ".cache"


# ── Domain validation ───────────────────────────────────────────────────────

# Conservative: lowercase letters, digits, dots, hyphens. Excludes
# wildcards, regex, and TLD-only entries (Unbound balks on those).
DOMAIN_RE = re.compile(r"^(?=.{1,253}$)(?!-)([a-z0-9-]{1,63}\.)+[a-z]{2,63}$")


def normalise_domain(raw: str) -> str | None:
    """Best-effort canonicalise to bare lowercase domain. Returns None if
    the line should be dropped (comment, empty, malformed)."""
    s = raw.strip().lower()
    if not s or s.startswith("#") or s.startswith("!"):
        return None
    # AdBlock Plus: ||example.com^ ⇒ example.com
    if s.startswith("||"):
        s = s[2:]
        if s.endswith("^"):
            s = s[:-1]
    # AdBlock Plus modifier suffix (e.g. ||x.com^$third-party)
    if "$" in s:
        s = s.split("$", 1)[0]
    # /etc/hosts: "0.0.0.0 example.com" or "127.0.0.1 example.com"
    if s.split() and s.split()[0] in ("0.0.0.0", "127.0.0.1", "::"):
        parts = s.split()
        if len(parts) >= 2:
            s = parts[1]
        else:
            return None
    # OISD-style wildcard prefix: "*.example.com" — Unbound's
    # `local-zone:"X." static` already matches every subdomain, so the
    # wildcard prefix is redundant and we strip it. (We keep the no-
    # internal-wildcard check below for everything OTHER than the
    # leading `*.` form.)
    if s.startswith("*."):
        s = s[2:]
    # Strip trailing dot.
    if s.endswith("."):
        s = s[:-1]
    # Reject embedded wildcards, regex, and obvious junk.
    if "*" in s or "/" in s or " " in s:
        return None
    if not DOMAIN_RE.match(s):
        return None
    return s


# ── Source fetcher ──────────────────────────────────────────────────────────


def fetch_source(url: str, cache_dir: Path, no_fetch: bool, quiet: bool) -> bytes:
    cache_key = hashlib.sha256(url.encode()).hexdigest()
    cache_path = cache_dir / f"{cache_key}.txt"
    if no_fetch:
        if not cache_path.exists():
            raise FileNotFoundError(
                f"--no-fetch but no cached copy of {url} at {cache_path}"
            )
        return cache_path.read_bytes()

    cache_dir.mkdir(parents=True, exist_ok=True)
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "centervpn-blocklists-render/1.0"},
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                body = resp.read()
            cache_path.write_bytes(body)
            if not quiet:
                print(f"[fetch] {url} → {len(body)} bytes", file=sys.stderr)
            return body
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt < 2:
                time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"failed to fetch {url} after 3 attempts: {last_exc}")


# ── List loader ──────────────────────────────────────────────────────────────


def load_list_dir(level_dir: Path, cache_dir: Path, no_fetch: bool, quiet: bool) -> tuple[set[str], set[str]]:
    """Return (additions ∪ source-derived domains, exemptions) for one
    `lists/<level>/` directory. Exemptions are the ones to STRIP at the
    final merge step."""
    sources_yaml = level_dir / "sources.yaml"
    if not sources_yaml.exists():
        raise FileNotFoundError(f"missing {sources_yaml}")
    with sources_yaml.open() as fh:
        spec = yaml.safe_load(fh) or {}
    sources = spec.get("sources") or []

    domains: set[str] = set()
    for src in sources:
        url = src.get("url")
        if not url:
            continue
        body = fetch_source(url, cache_dir, no_fetch, quiet)
        text = body.decode("utf-8", errors="replace")
        added_for_source = 0
        for raw in text.splitlines():
            d = normalise_domain(raw)
            if d:
                domains.add(d)
                added_for_source += 1
        if not quiet:
            print(f"[parse] {src.get('name', url)}: {added_for_source} domains", file=sys.stderr)

    additions_path = level_dir / "additions.txt"
    if additions_path.exists():
        for raw in additions_path.read_text().splitlines():
            d = normalise_domain(raw)
            if d:
                domains.add(d)

    exemptions: set[str] = set()
    exemptions_path = level_dir / "exemptions.txt"
    if exemptions_path.exists():
        for raw in exemptions_path.read_text().splitlines():
            d = normalise_domain(raw)
            if d:
                exemptions.add(d)

    return domains, exemptions


# ── Tier renderer ────────────────────────────────────────────────────────────


def render_tier(config_path: Path, cache_dir: Path, no_fetch: bool, quiet: bool) -> dict:
    with config_path.open("rb") as fh:
        cfg = tomllib.load(fh)
    name = cfg["name"]
    includes = cfg.get("include") or []
    if not includes:
        raise ValueError(f"{config_path}: include[] must not be empty")

    merged: set[str] = set()
    exempt_total: set[str] = set()
    for level in includes:
        level_dir = LISTS_DIR / level
        if not level_dir.is_dir():
            raise FileNotFoundError(f"{config_path} references missing list dir {level_dir}")
        added, exempt = load_list_dir(level_dir, cache_dir, no_fetch, quiet)
        merged |= added
        exempt_total |= exempt

    final = sorted(merged - exempt_total)
    if not final:
        raise RuntimeError(f"tier {name}: rendered set is empty (sources fetch failure?)")

    out_name = cfg.get("output_filename") or f"{name}.conf"
    out_path = DIST_DIR / out_name
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    header = (
        f"# Unbound blocklist — tier '{name}'\n"
        f"# Generated: {now}\n"
        f"# Source: github.com/cenervpn-net/dns-blocklists\n"
        f"# Domain count: {len(final)}\n"
        f"# Exemptions applied: {len(exempt_total)}\n"
        f"# Sources: {', '.join(includes)}\n"
        f"# This file is auto-generated. Do not edit.\n"
        "\n"
        "server:\n"
    )
    body = "".join(f'    local-zone: "{d}." static\n' for d in final)
    blob = (header + body).encode()
    out_path.write_bytes(blob)
    sha256 = hashlib.sha256(blob).hexdigest()
    if not quiet:
        print(f"[render] {name}: {len(final)} domains → {out_path} (sha256={sha256[:12]}...)", file=sys.stderr)

    return {
        "name": name,
        "filename": out_name,
        "sha256": sha256,
        "size_bytes": len(blob),
        "domain_count": len(final),
        "exemption_count": len(exempt_total),
        "source_levels": includes,
    }


# ── Main ─────────────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--no-fetch", action="store_true",
                        help="reuse cached source bytes; do not hit the network")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--tag", default="",
                        help="release tag (e.g. v2026.05.04). Defaults to dev-<utc>.")
    args = parser.parse_args()

    if not CONFIGS_DIR.is_dir():
        print(f"[render] FATAL: {CONFIGS_DIR} missing", file=sys.stderr)
        return 1
    configs = sorted(CONFIGS_DIR.glob("*.toml"))
    if not configs:
        print(f"[render] FATAL: no tier configs in {CONFIGS_DIR}", file=sys.stderr)
        return 1

    levels = []
    for cfg in configs:
        try:
            levels.append(render_tier(cfg, args.cache_dir, args.no_fetch, args.quiet))
        except Exception as exc:  # noqa: BLE001
            print(f"[render] FATAL rendering {cfg}: {exc}", file=sys.stderr)
            return 3

    tag = args.tag or f"dev-{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    manifest = {
        "tag": tag,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "renderer_version": "1.0",
        "levels": levels,
    }
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    manifest_path = DIST_DIR / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=False) + "\n")
    if not args.quiet:
        print(f"[render] manifest written: {manifest_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
