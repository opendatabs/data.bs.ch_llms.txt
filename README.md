# data.bs.ch llms.txt toolkit

Maintainer toolkit for generating and validating LLM-facing docs for `data.bs.ch`.

## What this repository does

- Publishes a concise root `llms.txt` router.
- Generates dataset indexes for LLM navigation:
  - `llms/datasets/index.md`
  - `llms/datasets/by-theme/index.md`
  - `llms/datasets/by-theme/*.md`
- Validates required structure and links before publishing.

## Architecture

- `llms.txt`: root routing manifest for LLMs.
- `llms/*.md`: hand-authored guides.
- `scripts/generate_dataset_docs.py`: builds dataset index pages.
- `scripts/validate_llms_docs.py`: checks required files/sections and link integrity.
- `.github/workflows/validate-llms-docs.yml`: CI validation workflow.
- `.github/workflows/refresh-llms-datasets.yml`: scheduled generation + PR workflow.

## Data source strategy

`scripts/generate_dataset_docs.py` uses `huwise-utils-py` only.
If data loading fails, generation fails with an error.

## Prerequisites

- `uv` installed
- Python `3.12+` (see `.python-version`)

## Setup (uv)

```bash
uv sync
```

## Common commands (uv)

Generate dataset docs:

```bash
uv run python scripts/generate_dataset_docs.py
```

Validate docs:

```bash
uv run python scripts/validate_llms_docs.py
```

## CI behavior

- Validation workflow (`validate-llms-docs.yml`):
  - `uv sync --frozen`
  - generate docs
  - validate docs and links
- Refresh workflow (`refresh-llms-datasets.yml`):
  - scheduled daily
  - regenerates dataset docs
  - opens a PR with generated changes

## Publish/deploy checklist

1. Ensure root file is reachable at `/llms.txt`.
2. Ensure linked docs are reachable at:
   - `/llms/getting-started.md`
   - `/llms/odsql-cheatsheet.md`
   - `/llms/query-cookbook.md`
   - `/llms/datasets/index.md`
3. Run local generate + validate commands.
4. Confirm CI passes.
5. Spot-check a few generated theme pages and dataset rows.

## Troubleshooting

- Missing required root links in validator
  - Ensure `llms.txt` includes absolute URLs for all critical docs.
- Broken local links
  - Run validator and fix target paths in markdown.
- Dataset count changes unexpectedly
  - Verify portal availability and check Huwise API connectivity.
