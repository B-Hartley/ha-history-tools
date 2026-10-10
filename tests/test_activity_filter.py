"""Regression tests for history activity interpretation.

Run in an environment with Home Assistant installed:
    pytest -q tests/test_activity_filter.py
"""

from custom_components.ha_history_tools.history import summarize_activity_events


def event(entity, state, second):
    return {
        "entity_id": entity,
        "state": state,
        "changed_at": f"2026-10-10T15:00:{second:02d}+01:00",
    }


def test_door_openings_only():
    entity = "binary_sensor.sophies_bedroom_door"
    events = [
        event(entity, "off", 0), event(entity, "on", 1),
        event(entity, "off", 5), event(entity, "on", 8),
        event(entity, "off", 10),
    ]
    filtered, count = summarize_activity_events(events, 50)
    assert count == 2
    assert [e["state"] for e in filtered] == ["on", "on"]


def test_restarts_and_sensor_recovery_are_not_motion():
    entity = "binary_sensor.hall_person_detected"
    events = [
        event(entity, "off", 0),
        event(entity, "unavailable", 10),
        event(entity, "on", 12),  # restored state, not confirmed new activity
        event(entity, "off", 15),
        event(entity, "unknown", 20),
        event(entity, "on", 21),  # restored state, not confirmed new activity
        event(entity, "off", 22),
        event(entity, "on", 25),  # known off -> on, a real transition
    ]
    filtered, count = summarize_activity_events(events, 50)
    assert count == 1
    assert filtered[0]["changed_at"].endswith("25+01:00")


def test_person_location_change_discards_unknown():
    entity = "person.sophie_hartley"
    events = [
        event(entity, "home", 0),
        event(entity, "unknown", 10),
        event(entity, "home", 12),
        event(entity, "work", 20),
        event(entity, "work", 21),
        event(entity, "home", 30),
    ]
    filtered, count = summarize_activity_events(events, 50)
    assert count == 2
    assert [e["state"] for e in filtered] == ["work", "home"]


def test_limit_applies_after_filtering():
    entity = "binary_sensor.front_door"
    events = [
        event(entity, "off", 0), event(entity, "on", 1),
        event(entity, "off", 2), event(entity, "on", 3),
    ]
    filtered, count = summarize_activity_events(events, 1)
    assert count == 2
    assert len(filtered) == 1
    assert filtered[0]["changed_at"].endswith("03+01:00")

def test_moira_short_home_restart_blip_is_ignored():
    entity = "person.moira_hunt"
    events = [
        event(entity, "Sycam", 0),
        event(entity, "home", 10),
        event(entity, "Sycam", 13),
    ]
    filtered, count = summarize_activity_events(events, 50)
    assert count == 0
    assert filtered == []


def test_moira_genuine_home_stay_is_kept():
    entity = "person.moira_hunt"
    events = [
        event(entity, "Sycam", 0),
        event(entity, "home", 1),
        {"entity_id": entity, "state": "Sycam", "changed_at": "2026-10-10T15:05:00+01:00"},
    ]
    filtered, count = summarize_activity_events(events, 50)
    assert count == 2
    assert [item["state"] for item in filtered] == ["home", "Sycam"]
