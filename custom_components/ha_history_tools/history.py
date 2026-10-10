"""Recorder history with strict live Assist exposure enforcement."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from homeassistant.components.homeassistant.exposed_entities import async_should_expose
from homeassistant.components.recorder import get_instance, history
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import MAX_ENTITIES, MAX_EVENTS, MAX_HOURS

ASSISTANT = "conversation"


def permitted(hass: HomeAssistant, entity_id: str) -> bool:
    """Consult current Assist exposure on every call; never cache access."""
    if not isinstance(entity_id, str) or "." not in entity_id:
        return False
    if hass.states.get(entity_id) is None:
        return False
    try:
        return async_should_expose(hass, ASSISTANT, entity_id) is True
    except (KeyError, ValueError, RuntimeError):
        return False


def allowed_entities(hass: HomeAssistant, entities: list[str]) -> list[str]:
    """Reject the entire request if any entity is not exposed."""
    if not entities or len(entities) > MAX_ENTITIES or len(set(entities)) != len(entities):
        raise ValueError("Provide 1-20 distinct entity IDs")
    if not all(permitted(hass, entity) for entity in entities):
        raise PermissionError("One or more entities are not exposed to Assist")
    return entities


def validate_hours(hours: int) -> None:
    if isinstance(hours, bool) or not isinstance(hours, int) or not 1 <= hours <= MAX_HOURS:
        raise ValueError("hours must be an integer from 1 to 168")


async def read_history(
    hass: HomeAssistant, entities: list[str], hours: int, limit: int = MAX_EVENTS
) -> dict[str, Any]:
    """Read Recorder state changes; filter again before returning."""
    validate_hours(hours)
    allowed_entities(hass, entities)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_EVENTS:
        raise ValueError("limit must be an integer from 1 to 500")
    end = dt_util.utcnow()
    start = end - timedelta(hours=hours)
    result = await get_instance(hass).async_add_executor_job(
        history.get_significant_states,
        hass,
        start,
        end,
        entities,
        None,
        False,  # no synthetic state at beginning of period
        False,  # all state changes, not just 'significant' ones
        False,
        True,  # no attributes
    )
    # Exposure may have been revoked while Recorder was being queried.
    allowed_entities(hass, entities)
    records: list[dict[str, str]] = []
    for entity in entities:
        for state in result.get(entity, []):
            if not hasattr(state, "state"):
                continue
            records.append({
                "entity_id": entity,
                "state": state.state,
                "changed_at": dt_util.as_local(state.last_changed).isoformat(),
            })
    records.sort(key=lambda row: row["changed_at"])
    truncated = len(records) > limit
    if truncated:
        records = records[-limit:]
    return {
        "period_start": dt_util.as_local(start).isoformat(),
        "period_end": dt_util.as_local(end).isoformat(),
        "events": records,
        "truncated": truncated,
        "notice": "Only currently Assist-exposed entities; event times are local.",
    }


async def read_activity(hass: HomeAssistant, hours: int, limit: int) -> dict[str, Any]:
    """Query only exposed door, motion, occupancy and person entities."""
    candidates = [
        state.entity_id for state in hass.states.async_all()
        if (
            state.domain == "person"
            or (
                state.domain == "binary_sensor"
                and state.attributes.get("device_class")
                in {"door", "motion", "occupancy", "opening", "presence"}
            )
        )
        and permitted(hass, state.entity_id)
    ]
    if not candidates:
        return {"events": [], "notice": "No exposed activity entities"}
    validate_hours(hours)
    # Query chunks to keep calls bounded; ensure maximum entity count per batch.
    all_events: list[dict[str, str]] = []
    for offset in range(0, len(candidates), MAX_ENTITIES):
        result = await read_history(hass, candidates[offset:offset + MAX_ENTITIES], hours, MAX_EVENTS)
        all_events.extend(result["events"])
    # Check exposure *again* after collecting all batches, before any data leaves.
    all_events = [event for event in all_events if permitted(hass, event["entity_id"])]
    all_events.sort(key=lambda row: row["changed_at"])
    return {
        "events": all_events[-limit:],
        "truncated": len(all_events) > limit,
        "entity_count": len(candidates),
        "notice": "Events can indicate activity, not identify who caused it.",
    }
