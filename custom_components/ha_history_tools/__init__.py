"""Read-only Assist-exposure-aware history tools for Home Assistant."""

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Initialize tools loaded through the LLM platform."""
    return True
