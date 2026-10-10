"""Tests for one-call home bootstrap with exposure enforcement."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from custom_components.ha_history_tools.home_context import read_home_context


class States:
    def __init__(self, data):
        self.data = data

    def get(self, key):
        return self.data.get(key)


def test_bootstrap_reads_linked_exposed_summaries():
    start = SimpleNamespace(attributes={
        "live_summary_entity": "sensor.home_live_summary",
        "people_entity": "sensor.home_people_summary",
        "safety_entity": "sensor.hidden_summary",
    })
    hass = SimpleNamespace(states=States({"sensor.home_start_here": start}))
    with (
        patch("custom_components.ha_history_tools.home_context.permitted",
              side_effect=lambda hass, assistant, entity: entity != "sensor.hidden_summary"),
        patch("custom_components.ha_history_tools.home_context.read_entity_details",
              return_value={"entities": [{"entity_id": "sensor.home_start_here"}], "truncated": False}) as reader,
    ):
        result = read_home_context(hass, "conversation")
        assert "safety_entity" in result["skipped_summary_keys"]
        assert reader.call_args.args[2] == [
            "sensor.home_start_here", "sensor.home_live_summary",
            "sensor.home_people_summary",
        ]


def test_bootstrap_denies_hidden_start():
    hass = SimpleNamespace(states=States({}))
    with patch("custom_components.ha_history_tools.home_context.permitted", return_value=False):
        with pytest.raises(PermissionError):
            read_home_context(hass, "conversation")
