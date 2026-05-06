# CenterVPN DNS blocklists

Public source-of-truth for the DNS blocklists shipped to every CenterVPN
gateway. Inspired by Mullvad's
[`dns-blocklists`](https://github.com/mullvad/dns-blocklists) repo: small,
focused source files in `lists/`, declarative composition in `configs/`,
deterministic rendering by `scripts/render.py`, and signed releases that
gateways pull on a 15-minute timer over wg_mgmt.

## Repository structure

```
lists/
  advertising/
    sources.yaml       # remote source URLs + commit pinning
    additions.txt      # domains we want blocked but upstream lists miss
    exemptions.txt     # domains we never want blocked, even if upstream blocks them
  tracker/   { ... }
  malware/   { ... }
  gambling/  { ... }
  social/    { ... }
  privacy/   { ... }
configs/
  d2.toml              # advertising + tracker
  d3.toml              # everything
scripts/
  render.py            # composes lists/ → dist/<level>.conf
  validate.py          # invariant checks (no overlap, no malformed lines)
.github/workflows/
  ci.yml               # PR validation: render + diff + size check
  release.yml          # tag push → render → checksum → GitHub Release
dist/                  # render output (gitignored; CI artefact only)
```

## How the fleet consumes this

1. **CI on tag push** (e.g. `v2026.05.04`): `scripts/render.py` produces
   `dist/d2.conf`, `dist/d3.conf`, and `manifest.json` (sha256s, line
   counts, tag, UTC timestamp). Workflow attaches all three to a GitHub
   Release.
2. **Backend** polls `https://api.github.com/repos/cenervpn-net/dns-blocklists/releases/latest`
   every 5 minutes (`backendv2/internal/services/blocklist_sync_service.go`),
   verifies sha256s against `manifest.json`, caches under
   `/var/lib/centervpn/blocklists/<tag>/`, atomically updates the
   `current` symlink.
3. **Gateways** poll the backend's internal-API endpoints over wg_mgmt
   every 15 minutes (`vpn-gateway@gateway_api/blocklist_sync.py`):
   `GET /api/internal/gateway/blocklists/current` returns the target
   tag; `GET /api/internal/gateway/blocklists/<tag>/<level>` streams
   the file. The gateway atomically swaps
   `/dev/shm/dns/blocklist-<level>.conf` and reloads `unbound-<level>`.
4. **Reporting** is push: each gateway POSTs `{loaded_tag, lag, errors}`
   to `/api/internal/gateway/blocklists/report` after a successful
   apply. Admin UI surfaces the per-gateway sync status read-only.

The whole path preserves the wg_mgmt-only-post-enrolment invariant.
Gateways never reach out to the public internet for blocklist content;
the backend is the relay.

## Editing the lists

- Add a new source: edit the relevant `lists/<level>/sources.yaml` and
  open a PR. CI validates the URL is reachable and the format renders
  cleanly.
- Whitelist a false positive: add it to `lists/<level>/exemptions.txt`
  (one domain per line). The next render strips it from the merged set.
- Block something upstream missed: add it to
  `lists/<level>/additions.txt`.

## Cutting a release

Tag `v<YYYY>.<MM>.<DD>` (or `v<major>.<minor>.<patch>` for ad-hoc
patches). Push the tag. CI takes 2-3 minutes to render + checksum +
publish. The fleet picks up the new tag within 20 minutes (5-min
backend poll + 15-min gateway timer).

Recommended (guarded) workflow:

```bash
./scripts/release_blocklists.sh --tag v1.0.2 --push
```

The script enforces clean git state, validates tag format, runs
`validate.py` + tagged `render.py`, blocks duplicate tags, then pushes
the release tag.

For emergency rollback: delete the broken release in GitHub and the
backend will fall back to the previous "latest" on its next poll.

## Licensing

This repo is MIT-licensed. Upstream sources retain their own licenses;
each `sources.yaml` documents the license per source. The merged output
is a derivative work; we treat the merged output as MIT for our
purposes but downstream consumers should review per-source licenses if
they redistribute.
