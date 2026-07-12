"""Constants for the Notifications integration."""

from __future__ import annotations

DOMAIN = "btoddb_notifications"

# Config / option keys.
CONF_NOTIFY_SERVICE = "notify_service"

# The default notify target is intentionally generic so the component is shareable.
DEFAULT_NOTIFY_SERVICE = "notify.notify"
DEFAULT_CHANNEL = "BToddB Notifications"
