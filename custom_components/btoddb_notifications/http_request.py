"""
Pure HTTP notify-request handling — no Home Assistant imports (NT-7, NT-8).

This module is deliberately HA-free so its tests run under plain pytest, the same way
``sending.py`` is. It turns the JSON body and query string of a
``POST /api/btoddb_notifications/notify`` request into the fields the shared send
coroutine takes, and maps the outcome onto the HTTP status + JSON body. The Home
Assistant view in ``__init__.py`` only reads the request and calls into here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from http import HTTPStatus
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Mapping

# NT-8: the endpoint may only ever call a notify service. Home Assistant service names
# are lowercase slugs, so anything else (another domain, a bare "notify", a dotted
# path) is rejected before it can reach hass.services.
_NOTIFY_TARGET = re.compile(r"notify\.[a-z0-9_]+")

# String keys that may come from the query string as defaults; a body value for the
# same key wins (NT-7). message/actions/data are body-only.
_QUERY_KEYS = ("title", "channel", "tag", "target")

_ACTION_KEYS = frozenset({"action", "title"})


class NotifyRequestError(ValueError):
    """The request can't become a notification; ``reason`` is safe to return."""

    def __init__(self, reason: str) -> None:
        """Keep the short, client-facing ``reason``."""
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class NotifyFields:
    """The validated fields of one HTTP notify request (mirrors NT-2's inputs)."""

    message: str
    title: str | None = None
    channel: str | None = None
    tag: str | None = None
    actions: list[dict[str, str]] | None = None
    data: dict[str, object] | None = None
    target: str | None = None


def parse_notify_request(body: object, query: Mapping[str, str]) -> NotifyFields:
    """
    Validate one request's JSON ``body`` and ``query`` into ``NotifyFields`` (NT-7).

    Only ``message``, ``title``, ``channel``, ``tag``, ``actions``, ``data`` and
    ``target`` are read from the body; every other key is ignored, so a fixed-shape
    sender (e.g. a Grafana webhook) works as-is. A JSON ``null`` counts as absent.
    Raises ``NotifyRequestError`` on anything malformed, including a ``target`` that
    isn't ``notify.<service>`` (NT-8).
    """
    if not isinstance(body, dict):
        msg = "body must be a JSON object"
        raise NotifyRequestError(msg)

    message = body.get("message")
    if not isinstance(message, str) or not message.strip():
        msg = "message must be a non-empty string"
        raise NotifyRequestError(msg)

    strings = {key: _string_field(body, query, key) for key in _QUERY_KEYS}
    target = strings["target"]
    if target is not None and not _NOTIFY_TARGET.fullmatch(target):
        msg = "target must be notify.<service>"
        raise NotifyRequestError(msg)

    return NotifyFields(
        message=message,
        title=strings["title"],
        channel=strings["channel"],
        tag=strings["tag"],
        actions=_actions_field(body.get("actions")),
        data=_data_field(body.get("data")),
        target=target,
    )


async def handle_notify_request(
    body: object,
    query: Mapping[str, str],
    send: Callable[[NotifyFields], Awaitable[bool]],
    *,
    loaded: bool,
    target_exists: Callable[[str], bool],
) -> tuple[HTTPStatus, dict[str, object]]:
    """
    Run one HTTP notify request and return its ``(status, json_body)`` (NT-7, NT-8).

    503 when the config entry isn't loaded, 400 with a short ``error`` when the
    request is malformed or names a ``notify.<service>`` that ``target_exists`` says
    isn't registered, 502 when ``send`` reports the downstream notify call failed,
    otherwise 200.
    """
    if not loaded:
        return HTTPStatus.SERVICE_UNAVAILABLE, {
            "success": False,
            "error": "integration not loaded",
        }
    try:
        fields = parse_notify_request(body, query)
    except NotifyRequestError as err:
        return HTTPStatus.BAD_REQUEST, {"success": False, "error": err.reason}
    if fields.target is not None and not target_exists(fields.target):
        return HTTPStatus.BAD_REQUEST, {
            "success": False,
            "error": "unknown notify service",
        }
    if not await send(fields):
        return HTTPStatus.BAD_GATEWAY, {"success": False}
    return HTTPStatus.OK, {"success": True}


def _string_field(
    body: dict[object, object], query: Mapping[str, str], key: str
) -> str | None:
    """Return the body value for ``key``, else the query default; must be a string."""
    value = body.get(key)
    if value is None:
        value = query.get(key)
    if value is not None and not isinstance(value, str):
        msg = f"{key} must be a string"
        raise NotifyRequestError(msg)
    return value


def _actions_field(value: object) -> list[dict[str, str]] | None:
    """Validate ``actions`` as a list of ``{action, title}`` string dicts (NT-5)."""
    if value is None:
        return None
    if not isinstance(value, list) or not all(_is_action(item) for item in value):
        msg = "actions must be a list of {action, title} strings"
        raise NotifyRequestError(msg)
    return [dict(item) for item in value]


def _is_action(item: object) -> bool:
    return (
        isinstance(item, dict)
        and item.keys() == _ACTION_KEYS
        and all(isinstance(text, str) for text in item.values())
    )


def _data_field(value: object) -> dict[str, object] | None:
    """Validate ``data`` (notify-data overrides, NT-3) as a JSON object."""
    if value is None:
        return None
    if not isinstance(value, dict):
        msg = "data must be a JSON object"
        raise NotifyRequestError(msg)
    return value
