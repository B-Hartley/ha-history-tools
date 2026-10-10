"""Read-only Recorder queries checked against live Assist entity exposure."""

from __future__ import annotations

from datetime import timedelta
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


async def read_activity(
    hass: HomeAssistant, assistant: str | None, hours: int, limit: int
) -> dict[str, Any]:
    """Discover recent activity only among currently exposed sensor entities."""
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
    for offset in range(0, len(entities), MAX_ENTITIES):
        batch = entities[offset:offset + MAX_ENTITIES]
        result = await read_history(hass, assistant, batch, hours, MAX_EVENTS)
        events.extend(result["events"])
    # Revalidate after *all* queries, not only after individual batches.
    if any(not permitted(hass, assistant, event["entity_id"]) for event in events):
        raise PermissionError("Assist exposure changed during activity query; retry")
    events.sort(key=lambda event: event["changed_at"])
    return {
        "events": events[-limit:],
        "truncated": len(events) > limit,
        "entity_count": len(entities),
        "note": "Events indicate sensor activity, not who caused it.",
    }
