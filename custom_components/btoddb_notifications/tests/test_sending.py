"""Notify target parsing + payload building (NT-2, NT-3, NT-4, NT-5). HA-free."""

from __future__ import annotations

from conftest import load_module

sending = load_module("sending")
resolve_notify_target = sending.resolve_notify_target
build_notify_payload = sending.build_notify_payload

# ---------------------------------------------------------------------------
# resolve_notify_target() — parses "domain.service" into (domain, service).
# ---------------------------------------------------------------------------


def test_resolve_notify_target_parses_domain_and_service():
    assert resolve_notify_target("notify.mobile_app_x") == ("notify", "mobile_app_x")


def test_resolve_notify_target_defaults_domain_and_service_when_empty():
    assert resolve_notify_target("") == ("notify", "notify")


def test_resolve_notify_target_defaults_service_when_bare_domain():
    assert resolve_notify_target("notify") == ("notify", "notify")


def test_resolve_notify_target_parses_arbitrary_domain_and_service():
    assert resolve_notify_target("domain.service") == ("domain", "service")


# ---------------------------------------------------------------------------
# build_notify_payload() — the notify.* service-call payload shape.
# ---------------------------------------------------------------------------


def test_build_notify_payload_base_fields():
    payload = build_notify_payload("hello", None, "My Channel", None, None, None)
    assert payload == {
        "message": "hello",
        "data": {
            "ttl": 0,
            "priority": "high",
            "importance": "high",
            "channel": "My Channel",
        },
    }


def test_build_notify_payload_includes_title_only_when_given():
    with_title = build_notify_payload("hello", "Hi", "chan", None, None, None)
    assert with_title["title"] == "Hi"

    without_title = build_notify_payload("hello", None, "chan", None, None, None)
    assert "title" not in without_title


def test_build_notify_payload_includes_tag_only_when_given():
    with_tag = build_notify_payload("hello", None, "chan", "my-tag", None, None)
    assert with_tag["data"]["tag"] == "my-tag"

    without_tag = build_notify_payload("hello", None, "chan", None, None, None)
    assert "tag" not in without_tag["data"]


def test_build_notify_payload_includes_actions_only_when_given():
    actions = [{"action": "CLOSE", "title": "Close"}]
    with_actions = build_notify_payload("hello", None, "chan", None, actions, None)
    assert with_actions["data"]["actions"] == actions

    without_actions = build_notify_payload("hello", None, "chan", None, None, None)
    assert "actions" not in without_actions["data"]


def test_build_notify_payload_actions_pass_through_unchanged():
    actions = [{"action": "SNOOZE", "title": "Snooze"}, {"action": "OK", "title": "OK"}]
    payload = build_notify_payload("hello", None, "chan", None, actions, None)
    assert payload["data"]["actions"] is actions


def test_build_notify_payload_extra_data_overrides_base_keys():
    payload = build_notify_payload(
        "hello", None, "chan", None, None, {"priority": "normal"}
    )
    assert payload["data"]["priority"] == "normal"
    assert payload["data"]["ttl"] == 0
    assert payload["data"]["importance"] == "high"


def test_build_notify_payload_extra_data_merges_last_overriding_channel_tag_actions():
    payload = build_notify_payload(
        "hello",
        None,
        "chan",
        "tag1",
        [{"action": "A", "title": "A"}],
        {"channel": "override-chan", "tag": "override-tag", "actions": []},
    )
    assert payload["data"]["channel"] == "override-chan"
    assert payload["data"]["tag"] == "override-tag"
    assert payload["data"]["actions"] == []


def test_build_notify_payload_does_not_mutate_module_base_dict():
    original = dict(sending._NOTIFY_DATA)
    build_notify_payload(
        "hello", "title", "chan", "tag", [{"action": "A", "title": "A"}], {"x": 1}
    )
    assert original == sending._NOTIFY_DATA


def test_build_notify_payload_does_not_mutate_module_base_dict_across_calls():
    build_notify_payload("first", None, "chan-a", None, None, {"priority": "low"})
    second = build_notify_payload("second", None, "chan-b", None, None, None)
    assert second["data"]["priority"] == "high"
    assert second["data"]["channel"] == "chan-b"
