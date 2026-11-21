"""
The Notifications integration.

Extracted from ha-reminders (issue btoddb/ha-reminders#72): this integration owns a
single config entry holding a default notify target (``notify.*`` service) and exposes
a ``btoddb_notifications.send`` service that any other integration or automation can
call to push a high-priority notification, with optional actionable-notification
(tag/actions) passthrough (NT-1, NT-2). The same delivery path is exposed to other
apps over HTTP as ``POST /api/btoddb_notifications/notify`` (NT-7, NT-8).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import voluptuous as vol
from homeassistant.components.http import KEY_HASS, HomeAssistantView
from homeassistant.core import (
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.helpers import config_validation as cv

from .const import CONF_NOTIFY_SERVICE, DEFAULT_CHANNEL, DOMAIN
from .http_request import NotifyFields, handle_notify_request
from .sending import build_notify_payload, resolve_notify_target

if TYPE_CHECKING:
    from aiohttp import web
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

SERVICE_SEND = "send"
ATTR_MESSAGE = "message"
ATTR_TITLE = "title"
ATTR_CHANNEL = "channel"
ATTR_TAG = "tag"
ATTR_ACTIONS = "actions"
ATTR_DATA = "data"
ATTR_TARGET = "target"
ATTR_ACTION = "action"

# hass.data flag: HTTP views can't be unregistered, so the view is registered at most
# once per Home Assistant run and outlives config-entry reloads (NT-7).
DATA_VIEW_REGISTERED = f"{DOMAIN}_http_view_registered"

ACTION_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ACTION): cv.string,
        vol.Required(ATTR_TITLE): cv.string,
    }
)

SEND_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_MESSAGE): cv.string,
        vol.Optional(ATTR_TITLE): cv.string,
        vol.Optional(ATTR_CHANNEL): cv.string,
        vol.Optional(ATTR_TAG): cv.string,
        vol.Optional(ATTR_ACTIONS): [ACTION_SCHEMA],
        vol.Optional(ATTR_DATA): dict,
        vol.Optional(ATTR_TARGET): cv.string,
    }
)


def _notify_target_for(hass: HomeAssistant, call_target: str | None) -> tuple[str, str]:
    """
    Resolve the notify target to call.

    Per-call ``target`` overrides the configured default (NT-2). ``single_config_entry``
    guarantees at most one config entry.
    """
    if call_target:
        return resolve_notify_target(call_target)
    entries = hass.config_entries.async_entries(DOMAIN)
    configured = ""
    if entries:
        entry = entries[0]
        configured = (
            entry.options.get(CONF_NOTIFY_SERVICE)
            or entry.data.get(CONF_NOTIFY_SERVICE)
            or ""
        )
    return resolve_notify_target(configured)


async def async_send(  # noqa: PLR0913
    hass: HomeAssistant,
    *,
    message: str,
    title: str | None = None,
    channel: str | None = None,
    tag: str | None = None,
    actions: list[dict[str, str]] | None = None,
    data: dict[str, object] | None = None,
    target: str | None = None,
) -> bool:
    """
    Push one notification to the configured (or overridden) notify target.

    Shared by the ``send`` service and the HTTP view so both resolve the target
    (NT-1, NT-2) and build the payload (NT-3..NT-5) identically. Returns ``False`` and
    logs the exception rather than propagating it (NT-6): a failed downstream notify
    call must never abort the caller, but must still be observable.
    """
    domain, service = _notify_target_for(hass, target)
    payload = build_notify_payload(
        message, title, channel or DEFAULT_CHANNEL, tag, actions, data
    )
    try:
        await hass.services.async_call(domain, service, payload, blocking=True)
    except Exception:
        _LOGGER.exception("Failed to send notification %r", message)
        return False
    return True


class NotifyView(HomeAssistantView):
    """
    ``POST /api/btoddb_notifications/notify`` — send from another app (NT-7, NT-8).

    Any Home Assistant user's long-lived access token is accepted (``requires_auth``).
    Parsing, validation and status mapping live in the HA-free ``http_request``
    module; this view only reads the request and delivers via ``async_send``.
    """

    url = "/api/btoddb_notifications/notify"
    name = "api:btoddb_notifications:notify"
    requires_auth = True

    async def post(self, request: web.Request) -> web.Response:
        """Handle one notify request."""
        hass = request.app[KEY_HASS]
        try:
            body = await request.json()
        except ValueError:
            body = None  # not JSON at all: rejected as "body must be a JSON object"

        async def _send(fields: NotifyFields) -> bool:
            return await async_send(
                hass,
                message=fields.message,
                title=fields.title,
                channel=fields.channel,
                tag=fields.tag,
                actions=fields.actions,
                data=fields.data,
                target=fields.target,
            )

        def _target_exists(target: str) -> bool:
            # An explicit notify.<service> that isn't registered is the caller's
            # mistake (400), not a downstream failure (502) — NT-8.
            return hass.services.has_service(*resolve_notify_target(target))

        status, result = await handle_notify_request(
            body,
            request.query,
            _send,
            loaded=bool(hass.config_entries.async_loaded_entries(DOMAIN)),
            target_exists=_target_exists,
        )
        return self.json(result, status)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Notifications from a config entry."""
    _async_register_service(hass)
    _async_register_view(hass)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


@callback
def _async_register_service(hass: HomeAssistant) -> None:
    """Register ``btoddb_notifications.send`` (idempotent)."""
    if hass.services.has_service(DOMAIN, SERVICE_SEND):
        return

    async def _handle_send(call: ServiceCall) -> ServiceResponse:
        """
        Push one notification via ``async_send``; respond with ``{"success": bool}``.

        Failures are logged, never raised (NT-6), and stay observable via the response
        for callers that opt in with ``return_response=True``.
        """
        success = await async_send(
            hass,
            message=call.data[ATTR_MESSAGE],
            title=call.data.get(ATTR_TITLE),
            channel=call.data.get(ATTR_CHANNEL),
            tag=call.data.get(ATTR_TAG),
            actions=call.data.get(ATTR_ACTIONS),
            data=call.data.get(ATTR_DATA),
            target=call.data.get(ATTR_TARGET),
        )
        return {"success": success}

    hass.services.async_register(
        DOMAIN,
        SERVICE_SEND,
        _handle_send,
        schema=SEND_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )


@callback
def _async_register_view(hass: HomeAssistant) -> None:
    """
    Register the HTTP view once per Home Assistant run (NT-7).

    Views can't be unregistered, so after an unload the view stays routed and answers
    503 until the entry is loaded again.
    """
    if hass.data.get(DATA_VIEW_REGISTERED):
        return
    hass.http.register_view(NotifyView())
    hass.data[DATA_VIEW_REGISTERED] = True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:  # noqa: ARG001
    """
    Unload a config entry, removing the service (single_config_entry: max one).

    The HTTP view stays registered (views can't be removed) and answers 503 (NT-7).
    """
    hass.services.async_remove(DOMAIN, SERVICE_SEND)
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload when options (e.g. the notify target) change (NT-1)."""
    await hass.config_entries.async_reload(entry.entry_id)
