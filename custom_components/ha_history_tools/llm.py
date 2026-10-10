"""Contribute read-only history tools to the built-in Assist LLM API."""

from __future__ import annotations

import probatio

from homeassistant.components import llm
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import llm as llm_helpers

from .const import DOMAIN
from .history import read_activity, read_history


class EntityHistoryTool(llm_helpers.Tool):
    """Fetch Recorder state changes for specifically exposed entities."""

    name = "ha_history_tools__get_entity_history"
    title = "Get exposed entity history"
    description = (
        "Get chronological state changes over the last 1-168 hours for 1-20 exact "
        "entity IDs exposed to the Home Assistant conversation assistant. Read only."
    )
    integration = DOMAIN
    annotations = llm_helpers.ToolAnnotations(
        read_only=True, destructive=False, idempotent=True, open_world=False
    )
    parameters = probatio.Schema({
        probatio.Required("entity_ids"): [str],
        probatio.Optional("hours", default=24): probatio.All(int, probatio.Range(min=1, max=168)),
        probatio.Optional("limit", default=200): probatio.All(int, probatio.Range(min=1, max=500)),
    })

    async def async_call(
        self, hass: HomeAssistant, tool_input: llm_helpers.ToolInput, llm_context: llm_helpers.LLMContext
    ) -> llm_helpers.ToolResult:
        try:
            data = await read_history(
                hass, tool_input.tool_args["entity_ids"],
                tool_input.tool_args.get("hours", 24),
                tool_input.tool_args.get("limit", 200),
            )
            return llm_helpers.ToolResult(data=data)
        except (PermissionError, ValueError) as exc:
            return llm_helpers.ToolResult(data={"error": str(exc)}, error=True)


class RecentActivityTool(llm_helpers.Tool):
    """Read only exposed motion, door and person state changes."""

    name = "ha_history_tools__get_recent_activity"
    title = "Get exposed household activity"
    description = (
        "Recent door openings, motion, occupancy and presence changes from "
        "currently Assist-exposed entities only. Does not identify people from motion."
    )
    integration = DOMAIN
    annotations = llm_helpers.ToolAnnotations(
        read_only=True, destructive=False, idempotent=True, open_world=False
    )
    parameters = probatio.Schema({
        probatio.Optional("hours", default=2): probatio.All(int, probatio.Range(min=1, max=168)),
        probatio.Optional("limit", default=100): probatio.All(int, probatio.Range(min=1, max=500)),
    })

    async def async_call(
        self, hass: HomeAssistant, tool_input: llm_helpers.ToolInput, llm_context: llm_helpers.LLMContext
    ) -> llm_helpers.ToolResult:
        try:
            return llm_helpers.ToolResult(data=await read_activity(
                hass, tool_input.tool_args.get("hours", 2),
                tool_input.tool_args.get("limit", 100),
            ))
        except (PermissionError, ValueError) as exc:
            return llm_helpers.ToolResult(data={"error": str(exc)}, error=True)


@callback
def async_get_tools(
    hass: HomeAssistant, llm_context: llm_helpers.LLMContext, api_id: str
) -> llm.LLMTools | None:
    """Only contribute to the built-in Assist API, not arbitrary APIs."""
    if api_id != llm.LLM_API_ASSIST:
        return None
    return llm.LLMTools(
        tools=[EntityHistoryTool(), RecentActivityTool()],
        prompt="History tools query Recorder read-only and strictly respect live Assist entity exposure.",
    )
