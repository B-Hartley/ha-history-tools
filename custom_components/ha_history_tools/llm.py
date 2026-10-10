"""Assist LLM tools for safely querying exposed Recorder history."""

from __future__ import annotations

import logging

import probatio

from homeassistant.components.llm import LLMTools
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.llm import (
    LLM_API_ASSIST,
    LLMContext,
    Tool,
    ToolAnnotations,
    ToolInput,
    ToolResult,
)

from .const import DOMAIN
from .details import read_entity_details
from .home_context import read_home_context
from .history import read_activity, read_history

_LOGGER = logging.getLogger(__name__)

READ_ONLY = ToolAnnotations(
    read_only=True, destructive=False, idempotent=True, open_world=False
)


class EntityHistoryTool(Tool):
    """Read recent state changes for named exposed entities."""

    name = "ha_history_tools__get_entity_history"
    title = "Get exposed entity history"
    description = (
        "Read Home Assistant state changes for 1-20 exact entity IDs during "
        "the last 1-168 hours. Only entities currently exposed to this Assist "
        "assistant are allowed. Use for door opening and appliance history."
    )
    integration = DOMAIN
    annotations = READ_ONLY
    parameters = probatio.Schema({
        probatio.Required("entity_ids"): [str],
        probatio.Optional("hours", default=24): probatio.All(int, probatio.Range(min=1, max=168)),
        probatio.Optional("limit", default=200): probatio.All(int, probatio.Range(min=1, max=500)),
    })

    async def async_call(
        self, hass: HomeAssistant, tool_input: ToolInput, llm_context: LLMContext
    ) -> ToolResult:
        try:
            data = await read_history(
                hass, llm_context.assistant,
                tool_input.tool_args["entity_ids"],
                tool_input.tool_args.get("hours", 24),
                tool_input.tool_args.get("limit", 200),
            )
            return ToolResult(data=data)
        except (PermissionError, ValueError) as exc:
            return ToolResult(data={"error": str(exc)}, error=True)
        except Exception:
            _LOGGER.exception("Recorder entity history query failed")
            return ToolResult(data={"error": "Recorder query unavailable"}, error=True)


class RecentActivityTool(Tool):
    """Read recent activity from exposed sensor entities only."""

    name = "ha_history_tools__get_recent_activity"
    title = "Get exposed household activity"
    description = (
        "Recent recorded door, motion, occupancy and person state transitions "
        "from entities currently exposed to the requesting Assist assistant."
    )
    integration = DOMAIN
    annotations = READ_ONLY
    parameters = probatio.Schema({
        probatio.Optional("hours", default=2): probatio.All(int, probatio.Range(min=1, max=168)),
        probatio.Optional("limit", default=100): probatio.All(int, probatio.Range(min=1, max=500)),
    })

    async def async_call(
        self, hass: HomeAssistant, tool_input: ToolInput, llm_context: LLMContext
    ) -> ToolResult:
        try:
            data = await read_activity(
                hass, llm_context.assistant,
                tool_input.tool_args.get("hours", 2),
                tool_input.tool_args.get("limit", 100),
            )
            return ToolResult(data=data)
        except (PermissionError, ValueError) as exc:
            return ToolResult(data={"error": str(exc)}, error=True)
        except Exception:
            _LOGGER.exception("Recorder recent activity query failed")
            return ToolResult(data={"error": "Recorder query unavailable"}, error=True)


class EntityDetailsTool(Tool):
    """Return current state and bounded attributes for exposed entities."""

    name = "ha_history_tools__get_entity_details"
    title = "Get exposed entity details and attributes"
    description = (
        "Read current states and attributes for 1-10 exact entity IDs, including "
        "semantic Home Start Here guidance. Only currently Assist-exposed "
        "entities are allowed. Results may truncate oversized attributes."
    )
    integration = DOMAIN
    annotations = READ_ONLY
    parameters = probatio.Schema({
        probatio.Required("entity_ids"): [str],
    })

    async def async_call(
        self, hass: HomeAssistant, tool_input: ToolInput, llm_context: LLMContext
    ) -> ToolResult:
        try:
            data = read_entity_details(
                hass, llm_context.assistant, tool_input.tool_args["entity_ids"]
            )
            return ToolResult(data=data)
        except (PermissionError, ValueError) as exc:
            return ToolResult(data={"error": str(exc)}, error=True)
        except Exception:
            _LOGGER.exception("Exposed entity details query failed")
            return ToolResult(data={"error": "Entity details unavailable"}, error=True)


class HomeContextTool(Tool):
    """Fetch Home Start Here guidance and linked live summaries in one request."""

    name = "ha_history_tools__get_home_context"
    title = "Get complete home starting context"
    description = (
        "Recommended first tool call for a home status question. Reads Home "
        "Start Here plus up to nine linked, exposed summary sensors in one call. "
        "For past activity use history; for visual evidence use Frigate."
    )
    integration = DOMAIN
    annotations = READ_ONLY
    parameters = probatio.Schema({})

    async def async_call(
        self, hass: HomeAssistant, tool_input: ToolInput, llm_context: LLMContext
    ) -> ToolResult:
        try:
            return ToolResult(data=read_home_context(hass, llm_context.assistant))
        except (PermissionError, ValueError) as exc:
            return ToolResult(data={"error": str(exc)}, error=True)
        except Exception:
            _LOGGER.exception("Home context query failed")
            return ToolResult(data={"error": "Home context unavailable"}, error=True)


@callback
def async_get_tools(
    hass: HomeAssistant, llm_context: LLMContext, api_id: str
) -> LLMTools | None:
    """Only expose tools via Assist and only when an assistant is identified."""
    if api_id != LLM_API_ASSIST or not llm_context.assistant:
        return None
    return LLMTools(
        tools=[EntityHistoryTool(), RecentActivityTool(), EntityDetailsTool(), HomeContextTool()],
        prompt=(
            "The HA History Tools offer read-only Recorder history and current entity details for "
            "currently exposed entities. Do not infer person identity from "
            "motion events. Missing events are not proof of no movement."
        ),
    )
