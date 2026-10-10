"""Read-only Home Assistant history tools contributed to the Assist LLM API.

Enable with the following in configuration.yaml:

ha_history_tools:

This integration has no services and does not change Recorder or entity exposure.
"""

from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Activate this integration so HA can discover its llm.py platform."""
    return True
