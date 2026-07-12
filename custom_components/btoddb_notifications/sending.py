"""
Pure notification-building logic — no Home Assistant imports (NT-2, NT-3).

This module is deliberately HA-free so its tests run under plain pytest. It owns the
``domain.service`` target-parsing and the notify service-call payload shape shared by
every caller of ``btoddb_notifications.send``.
"""

from __future__ import annotations

# Notification presentation (NT-3): high-priority push so Android delivers immediately
# instead of holding it in Doze until the phone is unlocked. Channel is deliberately
# not included here — it is injected per-call so callers can keep their own Android
# channel identity (NT-4). Defined here (not const.py) and never imported elsewhere so
# this module has zero cross-module imports and can be loaded standalone by the test
# conftest shim, the same way reminders' delivery.py self-contains its constants.
_NOTIFY_DATA: dict[str, object] = {
    "ttl": 0,
    "priority": "high",
    "importance": "high",
}


def resolve_notify_target(configured: str) -> tuple[str, str]:
    """Parse ``domain.service`` into ``(domain, service)``."""
    domain, _, service = configured.partition(".")
    return (domain or "notify"), (service or "notify")


def build_notify_payload(  # noqa: PLR0913
    message: str,
    title: str | None,
    channel: str,
    tag: str | None,
    actions: list[dict[str, str]] | None,
    extra_data: dict[str, object] | None,
) -> dict[str, object]:
    """
    Build the full ``notify.*`` service-call payload for one notification.

    ``data`` starts from the base notify data (high-priority delivery, NT-3) plus
    ``channel``, then adds ``tag``/``actions`` when given (NT-5), and finally merges
    ``extra_data`` last so a caller can override anything, including the base keys
    (NT-3). ``title`` is only included in the payload when given. The module-level
    base dict is never mutated — a fresh dict is built on every call.
    """
    data: dict[str, object] = dict(_NOTIFY_DATA)
    data["channel"] = channel
    if tag:
        data["tag"] = tag
    if actions:
        data["actions"] = actions
    if extra_data:
        data.update(extra_data)

    payload: dict[str, object] = {"message": message, "data": data}
    if title is not None:
        payload["title"] = title
    return payload
