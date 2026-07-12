"""
The Notifications integration.

Extracted from ha-reminders (issue btoddb/ha-reminders#72): this integration owns a
single config entry holding a default notify target (``notify.*`` service) and exposes
a ``btoddb_notifications.send`` service that any other integration or automation can
call to push a high-priority notification, with optional actionable-notification
(tag/actions) passthrough (NT-1, NT-2).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import voluptuous as vol
from homeassistant.core import (
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.helpers import config_validation as cv

from .const import CONF_NOTIFY_SERVICE, DEFAULT_CHANNEL, DOMAIN
from .sending import build_notify_payload, resolve_notify_target

if TYPE_CHECKING:
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


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Notifications from a config entry."""
    _async_register_service(hass)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


@callback
def _async_register_service(hass: HomeAssistant) -> None:
    """Register ``btoddb_notifications.send`` (idempotent)."""
    if hass.services.has_service(DOMAIN, SERVICE_SEND):
        return

    async def _handle_send(call: ServiceCall) -> ServiceResponse:
        """
        Push one notification to the configured (or overridden) notify target.

        Returns ``{"success": False}`` and logs the exception rather than propagating
        it (NT-6): a failed downstream notify call must never abort the caller's
        automation, but must still be observable via the response for callers that
        opt in with ``return_response=True``.
        """
        message: str = call.data[ATTR_MESSAGE]
        domain, service = _notify_target_for(hass, call.data.get(ATTR_TARGET))
        payload = build_notify_payload(
            message,
            call.data.get(ATTR_TITLE),
            call.data.get(ATTR_CHANNEL) or DEFAULT_CHANNEL,
            call.data.get(ATTR_TAG),
            call.data.get(ATTR_ACTIONS),
            call.data.get(ATTR_DATA),
        )
        try:
            await hass.services.async_call(domain, service, payload, blocking=True)
        except Exception:
            _LOGGER.exception("Failed to send notification %r", message)
            return {"success": False}
        return {"success": True}

    hass.services.async_register(
        DOMAIN,
        SERVICE_SEND,
        _handle_send,
        schema=SEND_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:  # noqa: ARG001
    """Unload a config entry, removing the service (single_config_entry: max one)."""
    hass.services.async_remove(DOMAIN, SERVICE_SEND)
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload when options (e.g. the notify target) change (NT-1)."""
    await hass.config_entries.async_reload(entry.entry_id)
