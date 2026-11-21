"""
Shared ``async_send``, the ``send`` service and the HTTP view (NT-1..NT-8).

Unlike the other test modules this one imports the integration package, so it needs
Home Assistant installed (``requirements.txt``; CI installs it). It uses small fakes
for ``hass`` and the request instead of a full Home Assistant test harness.
"""

from __future__ import annotations

import asyncio
import importlib
import json
import logging
from types import SimpleNamespace

import pytest

pytest.importorskip("homeassistant")

from homeassistant.components.http import KEY_HASS

integration = importlib.import_module("custom_components.btoddb_notifications")

BASE_DATA = {"ttl": 0, "priority": "high", "importance": "high"}


class _FakeServices:
    def __init__(self, error=None, notify_services=("btoddb", "mobile_app_x")):
        self.error = error
        self.calls = []
        self.registered = {}
        self.notify_services = set(notify_services)

    async def async_call(self, domain, service, payload, blocking):
        self.calls.append((domain, service, payload, blocking))
        if self.error:
            raise self.error

    def has_service(self, domain, service):
        if domain == "notify" and service in self.notify_services:
            return True
        return (domain, service) in self.registered

    def async_register(self, domain, service, handler, **_options):
        self.registered[(domain, service)] = handler


class _FakeConfigEntries:
    def __init__(self, entries, loaded):
        self.entries = entries
        self.loaded = loaded

    def async_entries(self, _domain):
        return self.entries

    def async_loaded_entries(self, _domain):
        return self.entries if self.loaded else []


def _hass(configured="notify.btoddb", error=None, loaded=True, options=None):
    entry = SimpleNamespace(options=options or {}, data={"notify_service": configured})
    return SimpleNamespace(
        services=_FakeServices(error),
        config_entries=_FakeConfigEntries([entry], loaded),
        data={},
        http=SimpleNamespace(views=[], register_view=None),
    )


# ---------------------------------------------------------------------------
# async_send() — shared delivery path.
# ---------------------------------------------------------------------------


def test_async_send_uses_configured_target_and_default_channel():
    hass = _hass()
    assert asyncio.run(integration.async_send(hass, message="hi")) is True
    assert hass.services.calls == [
        (
            "notify",
            "btoddb",
            {"message": "hi", "data": {**BASE_DATA, "channel": "BToddB Notifications"}},
            True,
        )
    ]


def test_async_send_prefers_options_over_data():
    hass = _hass(options={"notify_service": "notify.from_options"})
    asyncio.run(integration.async_send(hass, message="hi"))
    assert hass.services.calls[0][:2] == ("notify", "from_options")


def test_async_send_per_call_target_and_fields():
    hass = _hass()
    actions = [{"action": "OK", "title": "Ok"}]
    asyncio.run(
        integration.async_send(
            hass,
            message="hi",
            title="T",
            channel="C",
            tag="t1",
            actions=actions,
            data={"priority": "normal"},
            target="notify.mobile_app_x",
        )
    )
    assert hass.services.calls == [
        (
            "notify",
            "mobile_app_x",
            {
                "message": "hi",
                "title": "T",
                "data": {
                    **BASE_DATA,
                    "priority": "normal",
                    "channel": "C",
                    "tag": "t1",
                    "actions": actions,
                },
            },
            True,
        )
    ]


def test_async_send_swallows_and_logs_downstream_errors(caplog):
    hass = _hass(error=RuntimeError("boom"))
    with caplog.at_level(logging.ERROR):
        assert asyncio.run(integration.async_send(hass, message="hi")) is False
    assert "Failed to send notification 'hi'" in caplog.text


# ---------------------------------------------------------------------------
# btoddb_notifications.send — unchanged behaviour on top of async_send.
# ---------------------------------------------------------------------------


def _send_handler(hass):
    integration._async_register_service(hass)
    return hass.services.registered[("btoddb_notifications", "send")]


def test_send_service_returns_success_and_passes_fields():
    hass = _hass()
    call = SimpleNamespace(data={"message": "hi", "target": "notify.x", "tag": "t"})
    assert asyncio.run(_send_handler(hass)(call)) == {"success": True}
    domain, service, payload, _ = hass.services.calls[0]
    assert (domain, service) == ("notify", "x")
    assert payload["data"]["tag"] == "t"


def test_send_service_reports_failure():
    hass = _hass(error=RuntimeError("boom"))
    call = SimpleNamespace(data={"message": "hi"})
    assert asyncio.run(_send_handler(hass)(call)) == {"success": False}


# ---------------------------------------------------------------------------
# NotifyView — POST /api/btoddb_notifications/notify.
# ---------------------------------------------------------------------------


class _FakeRequest:
    def __init__(self, hass, body=None, query=None, invalid_json=False):
        self.app = {KEY_HASS: hass}
        self.query = query or {}
        self._body = body
        self._invalid_json = invalid_json

    async def json(self):
        if self._invalid_json:
            msg = "not json"
            raise ValueError(msg)
        return self._body


def _post(request):
    response = asyncio.run(integration.NotifyView().post(request))
    return response.status, json.loads(response.body)


def test_view_contract():
    view = integration.NotifyView
    assert view.url == "/api/btoddb_notifications/notify"
    assert view.name == "api:btoddb_notifications:notify"
    assert view.requires_auth is True


def test_view_sends_and_returns_200():
    hass = _hass()
    request = _FakeRequest(
        hass, {"message": "hi", "title": "T", "status": "firing"}, {"channel": "C"}
    )
    assert _post(request) == (200, {"success": True})
    assert hass.services.calls == [
        (
            "notify",
            "btoddb",
            {"message": "hi", "title": "T", "data": {**BASE_DATA, "channel": "C"}},
            True,
        )
    ]


def test_view_invalid_json_is_400():
    hass = _hass()
    status, result = _post(_FakeRequest(hass, invalid_json=True))
    assert (status, result) == (
        400,
        {"success": False, "error": "body must be a JSON object"},
    )
    assert hass.services.calls == []


def test_view_never_calls_a_non_notify_service():
    hass = _hass()
    request = _FakeRequest(hass, {"message": "hi"}, {"target": "homeassistant.stop"})
    assert _post(request)[0] == 400
    assert hass.services.calls == []


def test_view_downstream_failure_is_502():
    hass = _hass(error=RuntimeError("boom"))
    assert _post(_FakeRequest(hass, {"message": "hi"})) == (502, {"success": False})


def test_view_unloaded_entry_is_503():
    hass = _hass(loaded=False)
    assert _post(_FakeRequest(hass, {"message": "hi"})) == (
        503,
        {"success": False, "error": "integration not loaded"},
    )
    assert hass.services.calls == []


def test_view_is_registered_once_per_run():
    hass = _hass()
    hass.http.register_view = hass.http.views.append
    integration._async_register_view(hass)
    integration._async_register_view(hass)
    assert len(hass.http.views) == 1
    assert isinstance(hass.http.views[0], integration.NotifyView)


def test_view_explicit_known_target_is_sent():
    hass = _hass()
    request = _FakeRequest(hass, {"message": "hi", "target": "notify.mobile_app_x"})
    assert _post(request) == (200, {"success": True})
    assert hass.services.calls[0][:2] == ("notify", "mobile_app_x")


@pytest.mark.parametrize(
    ("body", "query"),
    [
        ({"message": "hi", "target": "notify.nope"}, {}),
        ({"message": "hi"}, {"target": "notify.nope"}),
    ],
)
def test_view_unknown_notify_service_is_400_not_502(body, query):
    hass = _hass()
    assert _post(_FakeRequest(hass, body, query)) == (
        400,
        {"success": False, "error": "unknown notify service"},
    )
    assert hass.services.calls == []


def test_send_service_still_calls_unknown_target():
    # The send service is unchanged: no existence check, the call goes straight to
    # the downstream notify service (a real failure there is success False, NT-6).
    hass = _hass()
    call = SimpleNamespace(data={"message": "hi", "target": "notify.nope"})
    assert asyncio.run(_send_handler(hass)(call)) == {"success": True}
    assert hass.services.calls[0][:2] == ("notify", "nope")
