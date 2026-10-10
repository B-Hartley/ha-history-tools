"""One-call bootstrap context from Home Start Here and exposed summary entities."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from .details import read_entity_details
from .history import permitted

START_ENTITY = "sensor.home_start_here"
# Only these documented pointer attributes from Start Here are followed.
SUMMARY_KEYS = (
    "live_summary_entity", "people_entity", "safety_entity",
    "vehicle_entity", "energy_entity", "hot_tub_entity",
    "laundry_entity", "doorbell_entity", "maintenance_entity",
)
MAX_BOOTSTRAP = 10


def read_home_context(hass: HomeAssistant, assistant: str | None) -> dict[str, Any]:
    """Get the starting sensor and up to nine exposed, linked summaries.

    This deliberately follows only pre-defined attribute names, never arbitrary
    entity identifiers supplied by an attribute or user. Every result passes the
    regular live exposure checks, before and after it is read.
    """
    if not permitted(hass, assistant, START_ENTITY):
        raise PermissionError("Home Start Here is not exposed to this Assist assistant")
    start = hass.states.get(START_ENTITY)
    if start is None:
        raise PermissionError("Home Start Here is unavailable")

    ids = [START_ENTITY]
    skipped: list[str] = []
    for key in SUMMARY_KEYS:
        value = start.attributes.get(key)
        if not isinstance(value, str) or "." not in value or value in ids:
            continue
        if permitted(hass, assistant, value):
            ids.append(value)
        else:
            skipped.append(key)
        if len(ids) >= MAX_BOOTSTRAP:
            break

    result = read_entity_details(hass, assistant, ids)
    # Ensure Start Here was not revoked while querying linked entities.
    if not permitted(hass, assistant, START_ENTITY):
        raise PermissionError("Home Start Here exposure changed; retry")
    return {
        "context": result["entities"],
        "truncated": result["truncated"],
        "skipped_summary_keys": skipped,
        "note": (
            "One-call home bootstrap: current states and attributes only. "
            "History and Frigate are separate tools for investigating events. "
            "Only currently Assist-exposed entities are returned."
        ),
    }
