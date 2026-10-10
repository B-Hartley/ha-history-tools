"""Entity-details access and truncation tests, for a Home Assistant test environment."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from custom_components.ha_history_tools.details import read_entity_details


class FakeStates:
    def __init__(self, items):
        self.items = items

    def get(self, entity_id):
        return self.items.get(entity_id)


def state(entity_id, attributes=None):
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        entity_id=entity_id, name=entity_id, state="ready",
        attributes=attributes or {}, last_changed=now, last_updated=now,
    )


def test_details_return_attributes_for_exposed_entity():
    hass = SimpleNamespace(states=FakeStates({
        "sensor.home_start_here": state("sensor.home_start_here", {
            "history_guidance": "Use get_entity_history",
            "frigate_guidance": "Use Frigate for camera events",
        }),
    }))
    with patch("custom_components.ha_history_tools.details.allowed_entities") as allowed:
        result = read_entity_details(hass, "conversation", ["sensor.home_start_here"])
        assert result["entities"][0]["attributes"]["history_guidance"] == "Use get_entity_history"
        assert not result["truncated"]
        assert allowed.call_count == 2


def test_denied_entity_never_returns_details():
    hass = SimpleNamespace(states=FakeStates({
        "sensor.hidden": state("sensor.hidden", {"private": "secret"}),
    }))
    with patch(
        "custom_components.ha_history_tools.details.allowed_entities",
        side_effect=PermissionError("not exposed"),
    ):
        with pytest.raises(PermissionError):
            read_entity_details(hass, "conversation", ["sensor.hidden"])


def test_exposure_revocation_after_read_discards_result():
    hass = SimpleNamespace(states=FakeStates({
        "sensor.home_start_here": state("sensor.home_start_here", {"guidance": "text"}),
    }))
    with patch(
        "custom_components.ha_history_tools.details.allowed_entities",
        side_effect=[None, PermissionError("revoked")],
    ):
        with pytest.raises(PermissionError):
            read_entity_details(hass, "conversation", ["sensor.home_start_here"])


def test_oversized_attribute_is_not_returned():
    hass = SimpleNamespace(states=FakeStates({
        "sensor.home_start_here": state("sensor.home_start_here", {
            "huge": "x" * 7000, "small": "ok",
        }),
    }))
    with patch("custom_components.ha_history_tools.details.allowed_entities"):
        result = read_entity_details(hass, "conversation", ["sensor.home_start_here"])
        assert "huge" not in result["entities"][0]["attributes"]
        assert "huge" in result["entities"][0]["omitted_attributes"]
        assert result["truncated"] is True
