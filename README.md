# BToddB Notifications (Home Assistant custom component)

A reusable, high-priority notification-sending integration for Home Assistant. One
config entry holds a default notify target; any other integration or automation calls
the `btoddb_notifications.send` service to push a notification, with optional
actionable-notification (tag/actions) passthrough. Apps outside Home Assistant (e.g.
Grafana alerting) can push the same way over HTTP.

Extracted from [ha-reminders](https://github.com/btoddb/ha-reminders)
(issue [#72](https://github.com/btoddb/ha-reminders/issues/72)), which was sending
its own notify payloads inline; this integration pulls that logic out so any other
component can reuse it instead of reimplementing high-priority push delivery.

## What you get

- **`btoddb_notifications.send`** service:
  - `message` (required) — the notification body text.
  - `title` (optional) — included in the payload only when given.
  - `channel` (optional) — Android notification channel; defaults to
    `"BToddB Notifications"` so a caller extracted from another integration (like
    `ha-reminders`) can pass its own channel and keep its existing channel identity.
  - `tag` (optional) — notification tag, for de-duplication/replacement (HA
    Companion app only).
  - `actions` (optional) — list of `{action, title}` actionable-notification buttons
    (HA Companion app only).
  - `data` (optional) — arbitrary notify-data overrides, merged last so a caller can
    override anything, including the built-in `ttl`/`priority`/`importance`.
  - `target` (optional) — a `"domain.service"` override of the configured default
    notify target, for this call only.

  Returns `{"success": bool}` — call with `response_variable` (or
  `return_response: true`) if you need to know whether the downstream `notify.*` call
  actually succeeded.
- **`POST /api/btoddb_notifications/notify`** HTTP endpoint — the same send, for apps
  outside Home Assistant, authenticated with any valid HA access token (e.g. a
  long-lived access token). See
  [Send from another app (HTTP)](#send-from-another-app-http).
- **High-priority delivery** — every send goes out with `ttl: 0`, `priority: "high"`,
  `importance: "high"` so Android delivers it immediately instead of holding it in
  Doze. Per-call `data` can override any of these.

## Installation

### HACS (recommended)

1. HACS → ⋮ → **Custom repositories** → add `https://github.com/btoddb/ha-notifications`, category **Integration**.
2. Install **BToddB Notifications**, then restart Home Assistant.

### Manual

Copy `custom_components/btoddb_notifications/` into your HA config's
`custom_components/` directory and restart.

### Configure

**Settings → Devices & Services → Add Integration → BToddB Notifications.** The setup
picker is a dropdown of every **notify service** registered in your HA instance — pick
the one you want notifications delivered to by default. You can change it later from
the integration's **Configure** button; per-call `target` overrides it without
changing the default.

## Usage examples

Basic notification from an automation:

```yaml
automation:
  - alias: Garage door left open
    trigger:
      - trigger: state
        entity_id: binary_sensor.garage_door
        to: "on"
        for: "00:20:00"
    action:
      - action: btoddb_notifications.send
        data:
          title: Garage door
          message: The garage door has been open for 20 minutes.
```

Actionable notification with a per-call target override, checking the response:

```yaml
automation:
  - alias: Front door camera alert
    trigger:
      - trigger: state
        entity_id: binary_sensor.front_door_motion
        to: "on"
    action:
      - action: btoddb_notifications.send
        target: notify.mobile_app_pixel
        data:
          title: Front door
          message: Motion detected at the front door.
          tag: front-door-motion
          actions:
            - action: VIEW_CAMERA
              title: View camera
        response_variable: send_result
      - if:
          - condition: template
            value_template: "{{ not send_result.success }}"
        then:
          - action: persistent_notification.create
            data:
              message: Front door alert failed to send to the mobile app.
```

## Send from another app (HTTP)

Any app that can make an HTTP request can push a notification with
`POST /api/btoddb_notifications/notify`. It goes through exactly the same path as
`btoddb_notifications.send` (same default target, high-priority payload, channel).

**Token:** any valid Home Assistant access token works (e.g. a long-lived access
token). Create a dedicated **non-admin** Home Assistant user for the app (Settings →
People → Users → Add user, leave "Administrator" off), log in as that user, open its
profile → **Security** → **Long-lived access tokens** → **Create token**. Any user's
token works; a non-admin one limits what a leaked token can do.

**Body:** a JSON object. `message` is required; `title`, `channel`, `tag`, `actions`,
`data` and `target` work like the `send` fields above. **Any other key is ignored.**
`title`, `channel`, `tag` and `target` can also go in the query string as defaults — a
body value for the same key wins. `target` must be a `notify.<service>`; the endpoint
never calls anything else.

**Responses:**

| Status | Body | Meaning |
|---|---|---|
| 200 | `{"success": true}` | Sent. |
| 400 | `{"success": false, "error": "<reason>"}` | Bad request (not a JSON object, no `message`, wrong type, non-notify `target`). Nothing sent. |
| 400 | `{"success": false, "error": "unknown notify service"}` | `target` is a `notify.<service>` that doesn't exist in Home Assistant. Nothing sent. |
| 502 | `{"success": false}` | The downstream `notify.*` call failed (logged in HA). |
| 503 | `{"success": false, "error": "integration not loaded"}` | The integration's config entry isn't loaded. |
| 401 | — | Missing or bad token (Home Assistant's own auth). |

`curl` example:

```bash
curl -X POST "https://<ha-host>/api/btoddb_notifications/notify" \
  -H "Authorization: Bearer <long-lived-token>" \
  -H "Content-Type: application/json" \
  -d '{"title": "Backup", "message": "Nightly backup finished.", "target": "notify.mobile_app_pixel"}'
```

### Grafana alerting (webhook contact point)

Grafana's webhook contact point sends a fixed JSON body with top-level `title` and
`message` (plus many other keys, which are ignored), so no template work is needed:

1. Grafana → **Alerting** → **Contact points** → **Add contact point**, integration
   **Webhook**.
2. **URL:** `https://<ha-host>/api/btoddb_notifications/notify?channel=Fantasy%20alerts`
   (the query string sets the Android channel; add `&target=notify.<service>` to send
   somewhere other than the configured default).
3. **HTTP Method:** `POST`.
4. **Optional Webhook settings** → **Authorization Header - Scheme:** `Bearer`;
   **Authorization Header - Credentials:** the dedicated non-admin user's long-lived
   token.
5. If your Grafana version shows **Title**/**Message** fields under Optional Webhook
   settings, whatever they render becomes the notification's title and body;
   otherwise Grafana's default title and message are used.
6. **Test**, then **Save contact point**.

## How it behaves (spec)

The full, ID'd behavior spec lives in
[`requirements/spec/notifications.md`](requirements/spec/notifications.md) (rules
`NT-*`).

## Roadmap

- **Durable (ack/snooze-required) notifications** — an opt-in mode where a
  notification is considered undelivered until the recipient acknowledges or snoozes
  it, with sender feedback on outcome. **Not implemented yet** — today `send` (and the
  HTTP endpoint) is fire-and-forget: it reports whether the downstream `notify.*` call
  succeeded, not whether a human ever saw or acted on the notification.
