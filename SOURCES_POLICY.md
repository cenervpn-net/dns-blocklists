# Source intake policy

This repository uses a promise-first model similar to mature public DNS
blocklist projects: we define the product promise first, then only include
sources that match that promise.

## Acceptance criteria for new sources

A source is accepted only if all items are true:

1. Public, reachable URL over HTTPS.
2. Maintained by a known project/maintainer with update history.
3. License/usage terms are compatible with redistribution.
4. Scope matches one category (`advertising`, `tracker`, `malware`,
   `social`, `gambling`, `privacy`).
5. Data format is supported by our pipeline (`hosts` or `domains`).
6. Basic quality check passes (not empty, not obviously poisoned, no wild
   catch-all entries that violate tier promise).

## Placement rules

- DNS2-related feeds go to `advertising` and `tracker`.
- High-breakage or vendor-telemetry-heavy feeds go to DNS3 categories
  (`privacy`, `social`, etc.) unless explicitly approved otherwise.
- Do not place the same source in multiple categories.

## Verification workflow

For each source change:

1. Add/update entry in `lists/<category>/sources.yaml`.
2. Run `python3 scripts/validate.py`.
3. Render lists and inspect diff:
   - `python3 scripts/render.py`
   - check `build/<tier>.txt` size/delta and sample domains.
4. If delta is unusually large, require manual review before release.

## False-positive handling

- Add explicit allowlist entries to the relevant `exemptions.txt`.
- Prefer the narrowest exemption possible (single domain over wildcard).
- Record user-visible impact in PR description when exemption is urgent.

## Source removal policy

Remove a source if it becomes stale, unavailable, unlicensed, or noisy
(persistent false positives). Prefer removal over carrying a known-bad feed.
