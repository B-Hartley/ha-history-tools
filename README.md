# HA History Tools

Read-only Home Assistant Recorder history via the **built-in Assist / MCP Server**.

## Installation (Home Assistant 2026.10 preview)

1. Copy `custom_components/ha_history_tools` into Home Assistant's `/config/custom_components/`.
2. Add the following to your **configuration.yaml**:

   ```yaml
   ha_history_tools:
   ```

3. Use **Developer Tools -> YAML -> Check configuration**.
4. Restart Home Assistant.
5. Check **Settings -> System -> Logs** for any errors mentioning `ha_history_tools`.
6. Make sure your **Model Context Protocol Server** exposes the Assist LLM API and reconnect/refresh your ChatGPT connection. Look for tools `ha_history_tools__get_entity_history` and `ha_history_tools__get_recent_activity`.

There is **no Settings -> Devices & services configuration flow**. The `ha_history_tools:` YAML entry activates this initial version. No external port, token, database configuration or separate MCP instance is needed.

## Tools

- **Get entity history**: request exact entity IDs and a period (1-168 hours; default 24), returning state transitions and local timestamps.
- **Get recent activity**: look for recorded changes from exposed person, motion, door and occupancy entities (default two hours).

Recorder must be running and recording the requested sensors. Its own retention and exclusions still apply. Sensor data cannot establish who moved or prove an absence of movement.

## Security requirements

The tools use the **live Assist exposure list** associated with the actual requesting assistant, via `llm_context.assistant`. This is checked against Home Assistant's `async_should_expose` before and after querying. If no requesting assistant is identified, the tool is unavailable. A denied entity causes the entire explicit history request to fail. Activity searches only consider exposed entities. The uploaded text whitelist is **never read in production**.

**Important:** Check that the MCP connection uses the intended Assist assistant. Do not expose these tools through other broad APIs.

## First test sequence

1. Ask: "Has Sophie's bedroom door opened in the last hour?" Expect an event history from `binary_sensor.sophies_bedroom_door`.
2. Ask: "What activity has there been in the house during the last two hours?"
3. Ask for a deliberately *unexposed* entity's history; it must be denied.
4. Temporarily unexpose a test entity in Home Assistant Assist settings. Check that its history is denied on the next request, then restore exposure.

## Status

This is a first-test build, **not yet validated on a live HA 2026.10 instance**. If it fails to load or tools are absent, open an issue or share the Home Assistant logs. Do not use as a security enforcement mechanism until the unexposed-entity and revocation tests pass.

Logbook and statistics tools are not included in this first build.

## Recent activity filtering (PR #1 update)

The activity tool now reports only confirmed binary-sensor `off -> on` events and meaningful `person` location transitions. Initial readings and recovery from `unknown`/`unavailable` are ignored, avoiding false activity during Home Assistant restarts. Raw entity history remains unchanged for debugging. Filtering is deliberately conservative: an event at the very start of a query window with no previous known state will not be counted. The activity response reports source truncation if Recorder returns too many changes.

Regression cases are in `tests/test_activity_filter.py` (run with `pytest -q tests/test_activity_filter.py` in a Home Assistant development environment). The tests have not yet been executed against a HA 2026.10 installation.
