# GitHub workflow rules

`@btb` command routing, phase boundaries, shared tool defaults, and ship
semantics are owned by the reusable workflow in
`btoddb/btb-pipeline/.github/workflows/btb.yml@v1`.

This repository's `.github/workflows/btb-client.yml` is only the thin event caller
for that reusable workflow. Do not paste the shared command contract into this
repo's `AGENTS.md`, `CLAUDE.md`, or `ai-rules`; the pipeline injects it at
runtime so client repositories do not drift.

Keep local workflow guidance limited to facts specific to this repo:

- Python setup uses `python-version: "3.14"` and `pip install -r requirements.txt`.
- Code-changing phases may run `python3 -m pytest` and `scripts/lint` through the
  shared pipeline tool configuration.
- `scripts/ship` is the release hook used by `@btb ship`; it requires exactly
  one bump flag and supports `--public-release`.
