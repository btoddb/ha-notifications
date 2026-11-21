# Notifications — component spec

This is the spec for `btoddb_notifications`: the single config entry that owns a
default notify target, the `btoddb_notifications.send` service any other
integration or automation calls to push a notification, and the HTTP endpoint other
apps (e.g. Grafana alerting) call to do the same.

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
remain observable rather than silently swallowed. The HTTP endpoint (NT-7) shares this
delivery path — same target resolution, payload and exception handling — and reports a
failed push as HTTP 502 (NT-8).

## Send from another app (HTTP)

**NT-7.** `POST /api/btoddb_notifications/notify` lets any app push a notification
through the same delivery path as `send` (NT-1..NT-6).

- **Auth:** `Authorization: Bearer <token>` with any valid Home Assistant access token
  (e.g. a long-lived access token) of any user; the user does not need to be an admin.
- **Body:** must be a JSON object. Recognised keys: `message` (required, non-blank
  string), `title`, `channel`, `tag`, `target` (strings), `actions` (list of
  `{action, title}` objects, both strings, no other keys) and `data` (object). They
  mean the same as in `send` (NT-2). **Every other key is ignored**, so a sender with a
  fixed body (e.g. a Grafana webhook contact point, which sends top-level `title` and
  `message` plus many other keys) works as-is. A JSON `null` value counts as absent.
- **Query string:** `title`, `channel`, `tag` and `target` may be given as query
  parameters; they are defaults, and a body value for the same key overrides them.
  `message`, `actions` and `data` are body-only. Other query parameters are ignored.
- **Entry unloaded:** the view is registered once per Home Assistant run (views can't
  be unregistered). While the config entry is not loaded (unloaded, disabled, or
  mid-reload) it answers `503` with `{"success": false, "error": "integration not
  loaded"}` and sends nothing.

**NT-8 (constraint).** The HTTP `target` (body or query) must be `notify.<service>`,
where `<service>` is a lowercase slug (`[a-z0-9_]+`); anything else — another domain,
a bare `notify`, an empty string — is rejected with 400. The endpoint must never let a
caller invoke a non-notify service. Status codes:

- `200` `{"success": true}` — the downstream `notify.*` call succeeded.
- `400` `{"success": false, "error": "<short reason>"}` — body not a JSON object
  (including invalid JSON), `message` missing/blank/not a string, a field of the wrong
  type, malformed `actions`, a non-notify `target`, or an explicit well-formed
  `notify.<service>` target that isn't registered in Home Assistant (`"unknown notify
  service"`). Nothing is sent. (The `send` service does no such check; NT-2.)
- `502` `{"success": false}` — the downstream `notify.*` call raised; it is logged
  (NT-6).
- `503` — the config entry is not loaded (NT-7).
