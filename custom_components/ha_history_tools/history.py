"""Read-only Recorder queries checked against live Assist entity exposure."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from homeassistant.components.homeassistant import async_should_expose
from homeassistant.components.recorder import get_instance, history
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import MAX_ENTITIES, MAX_EVENTS, MAX_HOURS


def permitted(hass: HomeAssistant, assistant: str | None, entity_id: str) -> bool:
    """Only active entities exposed to the exact requesting assistant are permitted."""
    if not assistant or not isinstance(entity_id, str) or "." not in entity_id:
        return False
    if hass.states.get(entity_id) is None:
        return False
    try:
        return async_should_expose(hass, assistant, entity_id) is True
    except (KeyError, ValueError, RuntimeError):
        return False


def allowed_entities(hass: HomeAssistant, assistant: str | None, entities: list[str]) -> None:
    """Reject the whole request when a requested entity is not permitted."""
    if not isinstance(entities, list) or not 1 <= len(entities) <= MAX_ENTITIES:
        raise ValueError("Provide 1-20 exact entity IDs")
    if any(not isinstance(entity, str) for entity in entities):
        raise ValueError("Entity IDs must be strings")
    if len(set(entities)) != len(entities):
        raise ValueError("Entity IDs must not be repeated")
    if not all(permitted(hass, assistant, entity) for entity in entities):
        raise PermissionError("An entity is not exposed to this Assist assistant")


def validate_bounds(hours: int, limit: int) -> None:
    """Reject invalid ranges, including bool values."""
    if type(hours) is not int or not 1 <= hours <= MAX_HOURS:
        raise ValueError("hours must be from 1 to 168")
    if type(limit) is not int or not 1 <= limit <= MAX_EVENTS:
        raise ValueError("limit must be from 1 to 500")


async def read_history(
    hass: HomeAssistant,
    assistant: str | None,
    entities: list[str],
    hours: int,
    limit: int = 200,
) -> dict[str, Any]:
    """Read Recorder state transitions without requesting attributes."""
    validate_bounds(hours, limit)
    allowed_entities(hass, assistant, entities)
    end = dt_util.utcnow()
    start = end - timedelta(hours=hours)
    raw = await get_instance(hass).async_add_executor_job(
        history.get_significant_states,
        hass,
        start,
        end,
        entities,
        None,
        False,  # do not include state from before the time period
        False,  # include every state transition
        False,  # non-minimal State instances
        True,   # strip attributes
        False,  # not compressed
    )
    # Fail the entire request if exposure changed during database access.
    allowed_entities(hass, assistant, entities)
    events: list[dict[str, str]] = []
    for entity in entities:
        for state in raw.get(entity, []):
            events.append({
                "entity_id": entity,
                "state": state.state,
                "changed_at": dt_util.as_local(state.last_changed).isoformat(),
            })
    events.sort(key=lambda event: event["changed_at"])
    truncated = len(events) > limit
    return {
        "period_start": dt_util.as_local(start).isoformat(),
        "period_end": dt_util.as_local(end).isoformat(),
        "events": events[-limit:],
        "truncated": truncated,
        "total_events": len(events),
        "note": "States are sensor reports; motion cannot identify a person.",
    }


def summarize_activity_events(
    events: list[dict[str, str]], limit: int
) -> tuple[list[dict[str, str]], int]:
    """Keep meaningful transitions; discard initial/restore and unavailable noise.

    For binary sensors, a valid OFF -> ON transition is the useful activity
    event. For people, only transitions between two known, different
    locations count. A preceding unknown/unavailable state always breaks
    continuity, preventing startup restores from masquerading as activity.
    """
    per_entity: dict[str, list[dict[str, str]]] = {}
    for event in events:
        per_entity.setdefault(event["entity_id"], []).append(event)

    activity: list[dict[str, str]] = []
    for entity_id, changes in per_entity.items():
        changes.sort(key=lambda e: e["changed_at"])
        # Moira's tracker can briefly restore as 'home' after HA restarts.
        # Ignore only short home blips that are bracketed by known away states;
        # do not erase prolonged home visits or raw Recorder history.
        if entity_id == "person.moira_hunt":
            normalized = []
            for i, change in enumerate(changes):
                if (
                    change["state"] == "home"
                    and 0 < i < len(changes) - 1
                    and changes[i - 1]["state"] not in {"home", "unknown", "unavailable"}
                    and changes[i + 1]["state"] not in {"home", "unknown", "unavailable"}
                    and (
                        datetime.fromisoformat(changes[i + 1]["changed_at"])
                        - datetime.fromisoformat(change["changed_at"])
                    ).total_seconds() <= 120
                ):
                    continue
                normalized.append(change)
            changes = normalized
        prior: str | None = None
        for change in changes:
            state = change["state"]
            if state in {"unknown", "unavailable"}:
                prior = None
                continue
            if prior is None:
                prior = state
                continue
            if entity_id.startswith("binary_sensor."):
                if prior == "off" and state == "on":
                    activity.append({
                        **change,
                        "event": "activity_detected",
                    })
            elif entity_id.startswith("person.") and prior != state:
                activity.append({
                    **change,
                    "event": "location_changed",
                    "previous_state": prior,
                })
            prior = state
    activity.sort(key=lambda e: e["changed_at"])
    count = len(activity)
    return activity[-limit:], count


async def read_activity(
    hass: HomeAssistant, assistant: str | None, hours: int, limit: int
) -> dict[str, Any]:
    """Summarize genuine transitions on currently exposed activity entities."""
    validate_bounds(hours, limit)
    if not assistant:
        raise PermissionError("An Assist assistant context is required")
    entities = [
        state.entity_id
        for state in hass.states.async_all()
        if (
            state.domain == "person"
            or (
                state.domain == "binary_sensor"
                and state.attributes.get("device_class")
                in {"door", "motion", "occupancy", "opening", "presence"}
            )
        )
        and permitted(hass, assistant, state.entity_id)
    ]
    events: list[dict[str, str]] = []
    source_truncated = False
    for offset in range(0, len(entities), MAX_ENTITIES):
        batch = entities[offset:offset + MAX_ENTITIES]
        # Read *all* permitted events per batch, then discard restoration noise
        # before applying the user-facing activity result limit.
        result = await read_history(hass, assistant, batch, hours, MAX_EVENTS)
        source_truncated |= result["truncated"]
        events.extend(result["events"])
    # Fail closed if exposure changes anywhere during the multi-batch query.
    if any(not permitted(hass, assistant, entity) for entity in entities):
        raise PermissionError("Assist exposure changed during activity query; retry")
    filtered, count = summarize_activity_events(events, limit)
    return {
        "events": filtered,
        "truncated": count > limit or source_truncated,
        "source_truncated": source_truncated,
        "entity_count": len(entities),
        "note": (
            "Only known-state transitions count. Initial states and restoration "
            "from unavailable/unknown are ignored. A recorded motion or door "
            "event does not identify a person. Truncated source history may "
            "omit earlier activity."
        ),
    }
