# Contributing

Pull requests welcome. Most changes touch only `lists/` (sources or
exemptions); nothing else needs editing.

## Branching + PRs

1. Branch from `main`.
2. Edit `lists/<tier>/sources.yaml`, `additions.txt`, or `exemptions.txt`.
3. Run `python3 scripts/validate.py` locally — should print `OK`.
4. Optionally `python3 scripts/render.py --tag dev-test` to confirm
   your change produces sensible output.
5. Open a PR. CI (validate + render-smoke) runs automatically; the
   render artefact is attached to the PR for inspection.

## Adding a new source

1. Pick the right tier directory under `lists/` (or create a new one
   plus a corresponding entry in `configs/<tier>.toml`).
2. Add an entry to `sources.yaml` with all five required keys (`name`,
   `url`, `format`, `license`, `description`).
3. Verify the URL is HTTPS and reachable; CI rejects HTTP.
4. Open a PR — the render-smoke job will tell you if the source
   parses cleanly.

## Whitelisting a false positive

Add the exact bare domain to the relevant tier's `exemptions.txt`,
one per line. Comments (lines starting with `#`) are allowed.

## Reporting an issue

If a domain is wrongly blocked or wrongly allowed, please open a
GitHub Issue with:

- The exact domain
- Which tier (d2 or d3) you observed it under
- A short justification (links to upstream, screenshots, etc.)

The issue queue is the source of truth for "what should be
blocked / unblocked"; we only merge tier changes that have an
issue or PR backing them.
