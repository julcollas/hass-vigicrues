"""Config flow for Vigicrues integration."""
from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import parse_qs, urlparse

import requests
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
import homeassistant.helpers.config_validation as cv

from .const import CONF_STATIONS, DOMAIN, VIGICRUES_OBSERVATIONS_API

_LOGGER = logging.getLogger(__name__)


def extract_station_id(input_str: str) -> str:
    """Extract station ID from URL or return the ID if it's already an ID.

    Supported formats:
    - Direct ID: F704000101
    - URL with path: https://www.vigicrues.gouv.fr/station/F704000101
    """
    input_str = input_str.strip()

    # Check if it's a URL
    if input_str.startswith("http://") or input_str.startswith("https://"):
        parsed = urlparse(input_str)

        # Try to extract from query parameters (e.g., ?CdStationHydro=Y561501001)
        query_params = parse_qs(parsed.query)
        if "CdStationHydro" in query_params:
            return query_params["CdStationHydro"][0]

        # Try to extract from path (e.g., /station/Y561501001)
        path_parts = parsed.path.strip("/").split("/")
        if len(path_parts) > 0:
            # Take the last part of the path
            station_id = path_parts[-1]
            # Remove .php extension if present
            if station_id.endswith(".php"):
                station_id = path_parts[-2] if len(path_parts) > 1 else ""
            if station_id:
                return station_id

    # If not a URL, assume it's already a station ID
    return input_str


async def validate_station(hass: HomeAssistant, station_id: str) -> dict[str, Any]:
    """Validate a station ID by checking if it exists in the Vigicrues API."""
    params = {"CdStationHydro": station_id, "GrdSerie": "H"}

    try:
        response = await hass.async_add_executor_job(
            lambda: requests.get(VIGICRUES_OBSERVATIONS_API, params=params, timeout=10)
        )
        response.raise_for_status()
        data = response.json()

        if "Serie" not in data:
            raise InvalidStation

        serie_data = data.get("Serie")
        station_name = f"{serie_data.get('LbStationHydro')} - {serie_data.get('CdStationHydro')}"

        return {"station_id": station_id, "station_name": station_name}
    except requests.exceptions.RequestException as err:
        _LOGGER.error("Error validating station %s: %s", station_id, err)
        raise CannotConnect from err
    except Exception as err:
        _LOGGER.error("Unexpected error validating station %s: %s", station_id, err)
        raise InvalidStation from err


class VigicruesConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Vigicrues."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                # Parse the stations input (comma-separated)
                stations_input = user_input.get(CONF_STATIONS, "")
                raw_stations = [s.strip() for s in stations_input.split(",") if s.strip()]

                # Extract station IDs from URLs or direct IDs
                stations = [extract_station_id(s) for s in raw_stations]

                # Validate all stations if any provided
                for station_id in stations:
                    await validate_station(self.hass, station_id)

                return self.async_create_entry(
                    title="Vigicrues",
                    data={CONF_STATIONS: stations},
                )
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidStation:
                errors["base"] = "invalid_station"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_STATIONS, default=""): str,
                }
            ),
            description_placeholders={
                "stations_example": "F704000101, https://www.vigicrues.gouv.fr/station/F700000103"
            },
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> VigicruesOptionsFlow:
        """Get the options flow for this handler."""
        return VigicruesOptionsFlow(config_entry)


class VigicruesOptionsFlow(config_entries.OptionsFlowWithConfigEntry):
    """Handle options flow for Vigicrues."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                # Parse the stations input (comma-separated)
                stations_input = user_input.get(CONF_STATIONS, "")
                raw_stations = [s.strip() for s in stations_input.split(",") if s.strip()]

                # Extract station IDs from URLs or direct IDs
                stations = [extract_station_id(s) for s in raw_stations]

                # Validate all stations if any provided
                for station_id in stations:
                    await validate_station(self.hass, station_id)

                # Update the config entry
                self.hass.config_entries.async_update_entry(
                    self.config_entry,
                    data={CONF_STATIONS: stations},
                )

                return self.async_create_entry(title="", data={})
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidStation:
                errors["base"] = "invalid_station"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        # Get current stations from config entry
        current_stations = self.config_entry.data.get(CONF_STATIONS, [])
        stations_str = ", ".join(current_stations)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_STATIONS, default=stations_str): str,
                }
            ),
            description_placeholders={
                "stations_example": "F700000103, https://www.vigicrues.gouv.fr/station/F700000103"
            },
            errors=errors,
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidStation(HomeAssistantError):
    """Error to indicate the station ID is invalid."""
