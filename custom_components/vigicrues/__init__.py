"""The vigicrues component."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import CONF_STATIONS, DOMAIN
from .coordinator import VigicruesDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Vigicrues from a config entry."""
    _LOGGER.debug("Setting up Vigicrues integration")

    hass.data.setdefault(DOMAIN, {})

    # Create coordinators for each station
    coordinators: dict[str, VigicruesDataUpdateCoordinator] = {}
    stations = entry.data.get(CONF_STATIONS, [])

    for station_id in stations:
        coordinator = VigicruesDataUpdateCoordinator(hass, station_id)
        await coordinator.async_config_entry_first_refresh()
        coordinators[station_id] = coordinator

    hass.data[DOMAIN][entry.entry_id] = coordinators

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register update listener for options changes
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.debug("Unloading Vigicrues integration")

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the config entry when it has changed."""
    _LOGGER.debug("Reloading Vigicrues integration")

    # Get current stations before reload
    old_stations = set(hass.data[DOMAIN].get(entry.entry_id, {}).keys())
    new_stations = set(entry.data.get(CONF_STATIONS, []))

    # Remove devices for stations that were removed
    removed_stations = old_stations - new_stations
    if removed_stations:
        device_registry = dr.async_get(hass)
        for station_id in removed_stations:
            device = device_registry.async_get_device(
                identifiers={(DOMAIN, station_id)}
            )
            if device:
                _LOGGER.debug("Removing device for station %s", station_id)
                device_registry.async_remove_device(device.id)

    await hass.config_entries.async_reload(entry.entry_id)


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: ConfigEntry, device_entry: dr.DeviceEntry
) -> bool:
    """Remove a device from the integration."""
    # Extract station_id from device identifiers
    station_id = None
    for identifier in device_entry.identifiers:
        if identifier[0] == DOMAIN:
            station_id = identifier[1]
            break

    if station_id is None:
        return False

    # Remove station from config if present
    stations = list(entry.data.get(CONF_STATIONS, []))
    if station_id in stations:
        stations.remove(station_id)
        hass.config_entries.async_update_entry(
            entry,
            data={CONF_STATIONS: stations},
        )
        _LOGGER.debug("Removed station %s from configuration", station_id)

    return True
