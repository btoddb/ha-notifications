"""
Config flow for the Notifications integration.

A single config entry. The only setting is the default notify target the ``send``
service pushes to when a call doesn't override it with ``target`` (NT-1); it's a plain
service string (e.g. ``notify.btoddb``) so the component is shareable across installs.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import selector

from .const import CONF_NOTIFY_SERVICE, DEFAULT_NOTIFY_SERVICE, DOMAIN


def _notify_services(hass: HomeAssistant) -> list[str]:
    """Return the registered notify services as ``notify.<name>`` strings, sorted."""
    return sorted(
        f"notify.{name}" for name in hass.services.async_services_for_domain("notify")
    )


def _notify_selector(
    hass: HomeAssistant, default_notify: str
) -> selector.SelectSelector:
    # Build the dropdown from the live notify services. The current value is prepended
    # if it isn't in the list (e.g. an already-configured service that is temporarily
    # offline), so the options flow never silently resets an existing entry.
    options = _notify_services(hass)
    if default_notify and default_notify not in options:
        options = [default_notify, *options]
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=options,
            mode=selector.SelectSelectorMode.DROPDOWN,
        )
    )


def _user_schema(hass: HomeAssistant, default_notify: str) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_NOTIFY_SERVICE, default=default_notify): _notify_selector(
                hass, default_notify
            ),
        }
    )


def _options_schema(hass: HomeAssistant, default_notify: str) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_NOTIFY_SERVICE, default=default_notify): _notify_selector(
                hass, default_notify
            ),
        }
    )


class NotificationsConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the initial setup."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the (only) setup step: pick the default notify target."""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        if user_input is not None:
            return self.async_create_entry(
                title="BToddB Notifications", data=user_input
            )
        # Pass "" as the notify default so the picker starts with no pre-selection;
        # notify.notify would only appear as a phantom option if it isn't registered.
        return self.async_show_form(
            step_id="user",
            data_schema=_user_schema(self.hass, ""),
        )

    @staticmethod
    @callback
    def async_get_options_flow(_config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow handler (notify target is its only field)."""
        return NotificationsOptionsFlow()


class NotificationsOptionsFlow(OptionsFlow):
    """Allow changing the default notify target after setup."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the (only) options step: change the default notify target."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        current_notify = self.config_entry.options.get(
            CONF_NOTIFY_SERVICE
        ) or self.config_entry.data.get(CONF_NOTIFY_SERVICE, DEFAULT_NOTIFY_SERVICE)
        return self.async_show_form(
            step_id="init",
            data_schema=_options_schema(self.hass, current_notify),
        )
