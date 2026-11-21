"""HTTP notify-request parsing + status mapping (NT-7, NT-8). HA-free."""

from __future__ import annotations

import asyncio
from http import HTTPStatus

import pytest
from conftest import load_module

http_request = load_module("http_request")
NotifyFields = http_request.NotifyFields
NotifyRequestError = http_request.NotifyRequestError
parse_notify_request = http_request.parse_notify_request
handle_notify_request = http_request.handle_notify_request

# A Grafana 11.2 webhook contact-point body: fixed shape, can't be customised.
GRAFANA_BODY = {
    "receiver": "homelab-ha",
    "status": "firing",
    "orgId": 1,
    "alerts": [
        {
            "status": "firing",
            "labels": {"alertname": "DiskFull", "instance": "fantasy-prod"},
            "annotations": {"summary": "Disk 95% full"},
            "startsAt": "2026-11-21T10:00:00Z",
            "endsAt": "0001-01-01T00:00:00Z",
            "generatorURL": "https://grafana.homelab.lan/alerting/grafana/x/view",
            "fingerprint": "abc123",
            "silenceURL": "https://grafana.homelab.lan/alerting/silence/new",
            "dashboardURL": "",
            "panelURL": "",
            "values": {"A": 95},
            "valueString": "[ var='A' value=95 ]",
        }
    ],
    "groupLabels": {"alertname": "DiskFull"},
    "commonLabels": {"alertname": "DiskFull", "instance": "fantasy-prod"},
    "commonAnnotations": {"summary": "Disk 95% full"},
    "externalURL": "https://grafana.homelab.lan/",
    "version": "1",
    "groupKey": '{}:{alertname="DiskFull"}',
    "truncatedAlerts": 0,
    "title": "[FIRING:1] DiskFull (fantasy-prod)",
    "state": "alerting",
    "message": "**Firing**\n\nValue: A=95\nLabels:\n - alertname = DiskFull\n",
}


def _reason(body, query=None) -> str:
    with pytest.raises(NotifyRequestError) as excinfo:
        parse_notify_request(body, query or {})
    return excinfo.value.reason


# ---------------------------------------------------------------------------
# parse_notify_request() — accepted bodies.
# ---------------------------------------------------------------------------


def test_minimal_body_is_message_only():
    assert parse_notify_request({"message": "hi"}, {}) == NotifyFields(message="hi")


def test_all_recognised_body_keys_are_read():
    fields = parse_notify_request(
        {
            "message": "hi",
            "title": "T",
            "channel": "C",
            "tag": "tag1",
            "actions": [{"action": "OK", "title": "Ok"}],
            "data": {"priority": "normal"},
            "target": "notify.mobile_app_x",
        },
        {},
    )
    assert fields == NotifyFields(
        message="hi",
        title="T",
        channel="C",
        tag="tag1",
        actions=[{"action": "OK", "title": "Ok"}],
        data={"priority": "normal"},
        target="notify.mobile_app_x",
    )


def test_unknown_body_keys_are_dropped():
    fields = parse_notify_request(
        {"message": "hi", "receiver": "x", "alerts": [1, 2], "service": "stop"}, {}
    )
    assert fields == NotifyFields(message="hi")


def test_grafana_webhook_body_picks_up_title_and_message_only():
    fields = parse_notify_request(GRAFANA_BODY, {"channel": "Fantasy alerts"})
    assert fields == NotifyFields(
        message=GRAFANA_BODY["message"],
        title=GRAFANA_BODY["title"],
        channel="Fantasy alerts",
    )


def test_query_supplies_defaults():
    fields = parse_notify_request(
        {"message": "hi"},
        {
            "title": "QT",
            "channel": "QC",
            "tag": "qtag",
            "target": "notify.mobile_app_q",
        },
    )
    assert fields == NotifyFields(
        message="hi",
        title="QT",
        channel="QC",
        tag="qtag",
        target="notify.mobile_app_q",
    )


def test_body_overrides_query():
    fields = parse_notify_request(
        {
            "message": "hi",
            "title": "BT",
            "channel": "BC",
            "tag": "btag",
            "target": "notify.mobile_app_b",
        },
        {
            "title": "QT",
            "channel": "QC",
            "tag": "qtag",
            "target": "notify.mobile_app_q",
        },
    )
    assert fields == NotifyFields(
        message="hi",
        title="BT",
        channel="BC",
        tag="btag",
        target="notify.mobile_app_b",
    )


def test_body_null_falls_back_to_query():
    fields = parse_notify_request({"message": "hi", "title": None}, {"title": "QT"})
    assert fields.title == "QT"


def test_message_actions_data_are_body_only():
    fields = parse_notify_request(
        {"message": "body"},
        {"message": "query", "actions": "[]", "data": "{}"},
    )
    assert fields == NotifyFields(message="body")


def test_empty_actions_list_is_accepted():
    assert parse_notify_request({"message": "hi", "actions": []}, {}).actions == []


def test_actions_are_copied():
    action = {"action": "OK", "title": "Ok"}
    fields = parse_notify_request({"message": "hi", "actions": [action]}, {})
    assert fields.actions == [action]
    assert fields.actions[0] is not action


@pytest.mark.parametrize("target", ["notify.mobile_app_x", "notify.notify"])
def test_notify_target_is_accepted(target):
    fields = parse_notify_request({"message": "hi", "target": target}, {})
    assert fields.target == target


# ---------------------------------------------------------------------------
# parse_notify_request() — rejected bodies.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("body", [None, [], ["message"], "hi", 1, True])
def test_non_object_body_is_rejected(body):
    assert _reason(body) == "body must be a JSON object"


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"title": "no message"},
        {"message": None},
        {"message": ""},
        {"message": "   "},
        {"message": 1},
        {"message": ["hi"]},
    ],
)
def test_missing_empty_or_non_string_message_is_rejected(body):
    assert _reason(body) == "message must be a non-empty string"


@pytest.mark.parametrize("key", ["title", "channel", "tag", "target"])
@pytest.mark.parametrize("value", [1, True, ["x"], {"x": 1}])
def test_non_string_optional_field_is_rejected(key, value):
    assert _reason({"message": "hi", key: value}) == f"{key} must be a string"


@pytest.mark.parametrize(
    "actions",
    [
        "OK",
        {"action": "OK", "title": "Ok"},
        ["OK"],
        [{"action": "OK"}],
        [{"title": "Ok"}],
        [{"action": "OK", "title": 1}],
        [{"action": None, "title": "Ok"}],
        [{"action": "OK", "title": "Ok", "uri": "https://x"}],
        [{"action": "OK", "title": "Ok"}, "OK"],
    ],
)
def test_bad_actions_are_rejected(actions):
    assert (
        _reason({"message": "hi", "actions": actions})
        == "actions must be a list of {action, title} strings"
    )


@pytest.mark.parametrize("data", ["x", 1, ["priority"], True])
def test_non_object_data_is_rejected(data):
    assert _reason({"message": "hi", "data": data}) == "data must be a JSON object"


NON_NOTIFY_TARGETS = [
    "homeassistant.stop",
    "script.foo",
    "notify",
    "notify.",
    "",
    "notify.mobile_app_x.extra",
    "notify.Mobile",
    "notify.mobile app",
    " notify.mobile_app_x",
    "notify.mobile_app_x\n",
    "notifyx.foo",
    "persistent_notification.create",
]


@pytest.mark.parametrize("target", NON_NOTIFY_TARGETS)
def test_non_notify_target_in_body_is_rejected(target):
    assert (
        _reason({"message": "hi", "target": target})
        == "target must be notify.<service>"
    )


@pytest.mark.parametrize("target", NON_NOTIFY_TARGETS)
def test_non_notify_target_in_query_is_rejected(target):
    assert (
        _reason({"message": "hi"}, {"target": target})
        == "target must be notify.<service>"
    )


def test_body_target_wins_over_query_target_and_is_always_validated():
    # Body wins, so an overridden query value is never used — but a bad body target
    # always fails, even when the query default is good.
    fields = parse_notify_request(
        {"message": "hi", "target": "notify.mobile_app_x"},
        {"target": "homeassistant.stop"},
    )
    assert fields.target == "notify.mobile_app_x"
    assert (
        _reason(
            {"message": "hi", "target": "homeassistant.stop"},
            {"target": "notify.mobile_app_x"},
        )
        == "target must be notify.<service>"
    )


# ---------------------------------------------------------------------------
# handle_notify_request() — status + JSON body mapping.
# ---------------------------------------------------------------------------


class _FakeSend:
    def __init__(self, result=True):
        self.result = result
        self.calls = []

    async def __call__(self, fields):
        self.calls.append(fields)
        return self.result


KNOWN_TARGETS = {"notify.mobile_app_x"}


def _handle(body, query=None, send=None, loaded=True):
    send = send or _FakeSend()
    return asyncio.run(
        handle_notify_request(
            body,
            query or {},
            send,
            loaded=loaded,
            target_exists=KNOWN_TARGETS.__contains__,
        )
    )


def test_handle_success_is_200_and_sends_parsed_fields():
    send = _FakeSend()
    status, result = _handle(GRAFANA_BODY, {"channel": "Fantasy alerts"}, send)
    assert status == HTTPStatus.OK
    assert result == {"success": True}
    assert send.calls == [
        NotifyFields(
            message=GRAFANA_BODY["message"],
            title=GRAFANA_BODY["title"],
            channel="Fantasy alerts",
        )
    ]


def test_handle_bad_request_is_400_with_reason_and_never_sends():
    send = _FakeSend()
    status, result = _handle({"message": "hi", "target": "script.foo"}, send=send)
    assert status == HTTPStatus.BAD_REQUEST
    assert result == {"success": False, "error": "target must be notify.<service>"}
    assert send.calls == []


def test_handle_non_object_body_is_400():
    status, result = _handle(None)
    assert status == HTTPStatus.BAD_REQUEST
    assert result == {"success": False, "error": "body must be a JSON object"}


def test_handle_failed_send_is_502():
    status, result = _handle({"message": "hi"}, send=_FakeSend(result=False))
    assert status == HTTPStatus.BAD_GATEWAY
    assert result == {"success": False}


def test_handle_not_loaded_is_503_and_never_sends():
    send = _FakeSend()
    status, result = _handle({"message": "hi"}, send=send, loaded=False)
    assert status == HTTPStatus.SERVICE_UNAVAILABLE
    assert result == {"success": False, "error": "integration not loaded"}
    assert send.calls == []


def test_handle_not_loaded_wins_over_bad_request():
    status, _ = _handle(None, loaded=False)
    assert status == HTTPStatus.SERVICE_UNAVAILABLE


def test_handle_known_target_is_sent():
    send = _FakeSend()
    status, _ = _handle({"message": "hi"}, {"target": "notify.mobile_app_x"}, send)
    assert status == HTTPStatus.OK
    assert send.calls[0].target == "notify.mobile_app_x"


@pytest.mark.parametrize(
    ("body", "query"),
    [
        ({"message": "hi", "target": "notify.nope"}, {}),
        ({"message": "hi"}, {"target": "notify.nope"}),
    ],
)
def test_handle_unknown_notify_target_is_400_and_never_sends(body, query):
    send = _FakeSend()
    status, result = _handle(body, query, send)
    assert status == HTTPStatus.BAD_REQUEST
    assert result == {"success": False, "error": "unknown notify service"}
    assert send.calls == []


def test_handle_default_target_skips_existence_check():
    # No explicit target: the configured default is used and never 400s here.
    status, _ = _handle({"message": "hi"})
    assert status == HTTPStatus.OK
