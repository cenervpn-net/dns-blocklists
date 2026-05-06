# DNS tier promise

This file defines what each DNS mode must mean operationally. Source
selection and release decisions must preserve these promises.

## DNS1 (vanilla)

- No blocking.
- Baseline encrypted resolver behaviour only.
- Used as compatibility fallback and troubleshooting baseline.

## DNS2 (balanced privacy)

- Blocks ads and trackers.
- Low-breakage bias: avoid broad category blocking.
- Intended as default "daily-safe" privacy mode.

Backed by:

- `configs/d2.toml`
- `lists/advertising/*`
- `lists/tracker/*`

## DNS3 (maximum privacy)

- Includes DNS2.
- Adds malware/phishing, social, gambling, and privacy/telemetry coverage.
- Higher strictness and higher breakage risk are expected and acceptable.

Backed by:

- `configs/d3.toml`
- `lists/malware/*`
- `lists/social/*`
- `lists/gambling/*`
- `lists/privacy/*`

## Change-control rules

- A source that changes DNS2 breakage profile significantly must be reviewed
  as a product decision, not a routine list refresh.
- Aggressive feeds should be DNS3-only by default.
- False positives are fixed through `exemptions.txt` in the smallest relevant
  category first.
