"""The Switch2 integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from switch2 import Switch2ApiClient
from .const import CONF_EMAIL, CONF_PASSWORD
from .coordinator import Switch2Coordinator

PLATFORMS: list[Platform] = [Platform.SENSOR]

type Switch2ConfigEntry = ConfigEntry[Switch2Coordinator]


async def async_setup_entry(hass: HomeAssistant, entry: Switch2ConfigEntry) -> bool:
    """Set up Switch2 from a config entry."""
    client = Switch2ApiClient(
        entry.data[CONF_EMAIL],
        entry.data[CONF_PASSWORD],
    )

    coordinator = Switch2Coordinator(hass, client)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: Switch2ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator: Switch2Coordinator = entry.runtime_data
        await coordinator.client.close()
    return unload_ok
