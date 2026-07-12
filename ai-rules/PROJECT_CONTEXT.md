# Project Context

This file provides guidance to AI coding agents when working with code in this
repository.

## Project Overview

This repo is a single Home Assistant **custom integration**,
`btoddb_notifications` (HACS-installable), that owns a single config entry
holding a default notify target and exposes a `btoddb_notifications.send`
service any other integration or automation can call to push a high-priority
notification, with optional actionable-notification (tag/actions) passthrough.
It was extracted from `btoddb_ha_reminders`
([ha-reminders](https://github.com/btoddb/ha-reminders) issue #72), which is
adopting it as a dependency rather than owning notification delivery itself.

The repo is based on the `integration_blueprint` dev scaffold: `config/` is a
throwaway Home Assistant instance for local testing, `scripts/` holds dev
helpers, and `requirements.txt` pins the Home Assistant and lint toolchain.

Every directory under `custom_components/` **except `btoddb_notifications`** is
a **vendored third-party integration** kept only for local testing. Never
modify any of them. If any command, including `scripts/lint`, leaves changes
under one of these directories, revert them; never commit a diff outside
`btoddb_notifications`.

There is no Lovelace card, sensor, or other platform entity in this
integration — it is a service-only integration (`integration_type: service`).

## Implementation Details

- **Python version:** target Python version 3.14 or newer.
- **Ruff formatting:** format all Python code according to the ruff formatting
  rules.
- **Ruff linting:** make coding decisions with ruff linting rules in mind.

## Key Dev Commands

- **Run HA locally:** `scripts/develop` launches Home Assistant against
  `config/`. It runs in the foreground with `--debug` and does not return; to
  verify a change, background it and read `config/home-assistant.log`.
- **Lint:** `scripts/lint` runs ruff format plus ruff check/fix. It rewrites
  files, so expect working-tree changes after it runs.
- **Engine unit tests:** `python3 -m pytest` from the repo root. `pytest.ini`
  sets `testpaths`, and `conftest.py` inserts its own directory into `sys.path`
  so `load_module` is importable regardless of working directory.
- **Validate manifest/HACS:** `python3 -m script.hassfest` and the
  `.github/workflows/validate.yml` workflow.
- **Hassfest locally:** `scripts/validate` runs CI's Hassfest check
  (`ghcr.io/home-assistant/hassfest`) against the working tree. It requires
  Docker.

## Versioning

There is a **single version number**:

- **Integration:** `custom_components/btoddb_notifications/manifest.json`
  (`"version": "vX.Y.Z"` - the leading `v` is intentional). Bumped by
  `scripts/ship` when cutting a release. Unlike `ha-reminders`, there is no
  separate card version — this integration has no frontend card.
