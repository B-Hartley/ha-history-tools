# HA History Tools

Read-only historical Home Assistant sensor data through the built-in MCP Server and Assist LLM API.

## Initial preview

- `ha_history_tools__get_entity_history`: state changes for 1-20 named entity IDs, 1-168 hours.
- `ha_history_tools__get_recent_activity`: recent door, motion, occupancy and person events.
- Checks Home Assistant's live Assist (`conversation`) exposure at query time, both before and after Recorder access.
- Uses Recorder internally; no new REST token or runtime whitelist file.
- No write operations. Unexposed entities are denied.

## Installing for testing

Copy `custom_components/ha_history_tools` into `/config/custom_components`, then restart Home Assistant. Inspect MCP tool discovery before relying on this integration. This preview has not yet been exercised on a running Home Assistant 2026.10 instance.

## Limitations

Only entity history and recent activity are included at this stage; logbook and statistics require additional security testing. Entities missing from live state cannot be queried. Historical data is limited by Recorder retention. A movement event does not establish who moved.

## Security

Uses live exposure for the built-in conversation assistant, **never** `chatgpt_assist_whitelist.txt` at runtime. MCP should remain configured to use the built-in Assist API.
