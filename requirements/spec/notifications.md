# Notifications — component spec

This is the spec for `btoddb_notifications`: the single config entry that owns a
default notify target, and the `btoddb_notifications.send` service any other
integration or automation calls to push a notification.

Rule IDs are **stable** — add new IDs, never renumber or reuse. The `NT-*` numbering
is scoped to this repo (extracted from `ha-reminders`'s `RM-*` numbering, but starts
fresh here).

## Config entry

**NT-1 (constraint).** A single config entry (`single_config_entry: true`) owns the
default notify target: `notify_service`, a plain `"domain.service"` string (e.g.
`notify.btoddb`). It is changeable after setup via the options flow. Changing it
reloads the config entry so the new default takes effect immediately.

## The `send` service

**NT-2.** `btoddb_notifications.send` accepts:

- `message` (required) — the notification body text.
- `title` (optional) — included in the payload only when given.
- `channel` (optional) — Android notification channel; defaults to
  `"BToddB Notifications"` (NT-4).
- `tag` (optional) — notification tag, passed through to the notify data (NT-5).
- `actions` (optional) — list of `{action, title}` dicts, passed through to the notify
  data (NT-5).
- `data` (optional) — arbitrary notify-data overrides, merged last (NT-3).
- `target` (optional) — a `"domain.service"` string that overrides the configured
  default notify target for this call only.

## Delivery priority

**NT-3 (constraint).** Notifications are sent high-priority: `ttl: 0`,
`priority: "high"`, `importance: "high"` in the notify data, so Android delivers the
push immediately instead of deferring it in Doze. Per-call `data` is merged last and
may override any of these (or any other) key.

## Channel identity

**NT-4.** The notify data's `channel` defaults to `"BToddB Notifications"`. Callers
may pass their own `channel` so an extracted caller (e.g. `ha-reminders`, which used
`"BToddB Reminders"`) keeps its existing Android channel identity after being
migrated to call this service instead of sending its own notify payload.

## Actionable notifications

**NT-5.** `tag` and `actions` pass through to the notify payload's `data`. They are
honoured only by the Home Assistant Companion mobile app; other notify targets
(e.g. `notify.persistent_notification`) silently ignore them.

## Response contract

**NT-6 (constraint).** `send` is registered with `SupportsResponse.OPTIONAL` and
returns `{"success": bool}`. Exceptions raised by the downstream `notify.*` service
call are caught and logged, never propagated — a single failed push must not abort
the caller's automation. Callers that need to know whether the push actually went out
(e.g. to retry or keep a reminder pending) must call with
`return_response: true`/`response_variable` and check `success`; a failed push must
remain observable rather than silently swallowed.
