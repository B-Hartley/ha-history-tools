"""Read details of exposed entities without providing access to hidden entities."""

from __future__ import annotations

import json
import math
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .history import allowed_entities

MAX_DETAILS_ENTITIES = 10
MAX_ATTRIBUTE_CHARS = 6000
MAX_RESPONSE_CHARS = 36000
MAX_DEPTH = 5


def safe_value(value: Any, depth: int = 0) -> Any:
    """Turn common HA attributes into bounded JSON-compatible values."""
    if depth >= MAX_DEPTH:
        return "[nested value omitted]"
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else str(value)
    if isinstance(value, (list, tuple)):
        return [safe_value(v, depth + 1) for v in value[:100]]
    if isinstance(value, dict):
        return {str(k): safe_value(v, depth + 1) for k, v in list(value.items())[:100]}
    return str(value)


def read_entity_details(
    hass: HomeAssistant, assistant: str | None, entity_ids: list[str]
) -> dict[str, Any]:
    """Read states and attributes; recheck all access just before returning."""
    if not isinstance(entity_ids, list) or not 1 <= len(entity_ids) <= MAX_DETAILS_ENTITIES:
        raise ValueError("Provide 1-10 exact entity IDs")
    allowed_entities(hass, assistant, entity_ids)
    results: list[dict[str, Any]] = []
    remaining = MAX_RESPONSE_CHARS
    for entity_id in entity_ids:
        state = hass.states.get(entity_id)
        if state is None:
            raise PermissionError("A requested entity is no longer available")
        attributes: dict[str, Any] = {}
        omitted: list[str] = []
        for key, value in state.attributes.items():
            safe = safe_value(value)
            encoded = json.dumps(safe, ensure_ascii=False, default=str)
            if len(encoded) > MAX_ATTRIBUTE_CHARS or len(encoded) > remaining:
                omitted.append(str(key))
                continue
            remaining -= len(encoded)
            attributes[str(key)] = safe
        results.append({
            "entity_id": entity_id,
            "state": state.state,
            "name": state.name,
            "last_changed": dt_util.as_local(state.last_changed).isoformat(),
            "last_updated": dt_util.as_local(state.last_updated).isoformat(),
            "attributes": attributes,
            "omitted_attributes": omitted,
        })
    # Permission revocation invalidates the ENTIRE result, even if partially read.
    allowed_entities(hass, assistant, entity_ids)
    return {
        "entities": results,
        "truncated": any(row["omitted_attributes"] for row in results),
        "note": "Current state only; only entities currently exposed to this Assist assistant.",
    }
