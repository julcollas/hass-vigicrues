"""Config flow for Vigicrues integration."""
from __future__ import annotations

import logging
from typing import Any
from urllib.parse import parse_qs, urlparse

import requests
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import selector

from .const import (
    CONF_SCAN_INTERVAL,
    CONF_STATIONS,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    HUBEAU_STATIONS_API,
    SCAN_INTERVAL_OPTIONS,
    VIGICRUES_OBSERVATIONS_API,
)

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


async def search_stations(hass: HomeAssistant, search_term: str) -> dict[str, str]:
    """Search active stations by site name or watercourse through Hub'Eau."""
    stations: dict[str, dict[str, Any]] = {}
    fields = (
        "code_station,libelle_station,libelle_site,libelle_commune,"
        "libelle_cours_eau,en_service"
    )

    try:
        for search_field in ("libelle_site", "libelle_cours_eau"):
            response = await hass.async_add_executor_job(
                lambda field=search_field: requests.get(
                    HUBEAU_STATIONS_API,
                    params={
                        field: search_term,
                        "en_service": 1,
                        "fields": fields,
                        "size": 100,
                    },
                    timeout=10,
                )
            )
            response.raise_for_status()
            for station in response.json().get("data", []):
                station_id = station.get("code_station")
                if station_id:
                    stations[station_id] = station
    except requests.exceptions.RequestException as err:
        _LOGGER.error("Error searching stations through Hub'Eau: %s", err)
        raise CannotConnect from err

    choices: dict[str, str] = {}
    sorted_stations = sorted(
        stations.items(),
        key=lambda item: (item[1].get("libelle_commune") or "", item[0]),
    )[:100]
    for station_id, station in sorted_stations:
        name = (
            station.get("libelle_station") or station.get("libelle_site") or station_id
        )
        name = " ".join(name.split())
        parenthesis_index = name.rfind(" (")
        if parenthesis_index != -1 and name.endswith(")"):
            name = name[:parenthesis_index].rstrip()
        choices[station_id] = f"{name} [{station_id}]"

    return choices


class VigicruesConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Vigicrues."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Choose between station search and manual entry."""
        return self.async_show_menu(step_id="user", menu_options=["search", "manual"])

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure stations by ID or URL."""
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
            step_id="manual",
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

    async def async_step_search(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Find stations by site, commune, or watercourse name."""
        errors: dict[str, str] = {}

        if user_input is not None:
            search_term = user_input.get("search", "").strip()
            if not search_term:
                errors["base"] = "search_required"
            else:
                try:
                    self._station_options = await search_stations(
                        self.hass, search_term
                    )
                    if not self._station_options:
                        errors["base"] = "no_stations_found"
                    else:
                        return await self.async_step_select_stations()
                except CannotConnect:
                    errors["base"] = "search_unavailable"

        return self.async_show_form(
            step_id="search",
            data_schema=vol.Schema(
                {
                    vol.Optional("search", default=""): str,
                }
            ),
            errors=errors,
        )

    async def async_step_select_stations(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Add selected stations after validating them against Vigicrues."""
        errors: dict[str, str] = {}

        if user_input is not None:
            stations = user_input.get(CONF_STATIONS, [])
            self._selected_stations = stations
            if not stations:
                errors["base"] = "no_stations_selected"
            else:
                try:
                    for station_id in stations:
                        await validate_station(self.hass, station_id)
                    return self.async_create_entry(
                        title="Vigicrues",
                        data={CONF_STATIONS: stations},
                    )
                except CannotConnect:
                    errors["base"] = "cannot_connect"
                except InvalidStation:
                    errors["base"] = "station_unavailable"

        return self.async_show_form(
            step_id="select_stations",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_STATIONS,
                        default=getattr(self, "_selected_stations", []),
                    ): cv.multi_select(self._station_options),
                }
            ),
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
        menu_options = ["manage_stations", "set_scan_interval"]
        if self.config_entry.data.get(CONF_STATIONS, []):
            menu_options.append("remove_stations")

        return self.async_show_menu(step_id="init", menu_options=menu_options)

    async def async_step_manage_stations(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Search for a station or add it by ID or URL."""
        errors: dict[str, str] = {}

        if user_input is not None:
            search_term = user_input.get("search", "").strip()
            station_input = user_input.get("station_id", "").strip()

            if search_term and station_input:
                errors["base"] = "choose_one_input"
            elif search_term:
                try:
                    self._station_options = await search_stations(
                        self.hass, search_term
                    )
                    if not self._station_options:
                        errors["base"] = "no_stations_found"
                    else:
                        return await self.async_step_add_searched_stations()
                except CannotConnect:
                    errors["base"] = "search_unavailable"
            elif station_input:
                stations = list(self.config_entry.data.get(CONF_STATIONS, []))
                station_id = extract_station_id(station_input)
                if station_id in stations:
                    errors["base"] = "already_added"
                else:
                    try:
                        await validate_station(self.hass, station_id)
                    except CannotConnect:
                        errors["base"] = "cannot_connect"
                    except InvalidStation:
                        errors["base"] = "invalid_station"
                    else:
                        stations.append(station_id)
                        self.hass.config_entries.async_update_entry(
                            self.config_entry,
                            data={**self.config_entry.data, CONF_STATIONS: stations},
                        )
                        return self.async_create_entry(title="", data={})
            else:
                errors["base"] = "search_or_station_required"

        return self.async_show_form(
            step_id="manage_stations",
            data_schema=vol.Schema(
                {
                    vol.Optional("search", default=""): str,
                    vol.Optional("station_id", default=""): str,
                }
            ),
            description_placeholders={
                "stations_example": "F700000103 or https://www.vigicrues.gouv.fr/station/F700000103"
            },
            errors=errors,
        )

    async def async_step_remove_stations(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Remove selected stations without changing the remaining ones."""
        errors: dict[str, str] = {}
        current_stations = list(self.config_entry.data.get(CONF_STATIONS, []))
        device_registry = dr.async_get(self.hass)
        station_options: dict[str, str] = {}

        for station_id in current_stations:
            device = device_registry.async_get_device(
                identifiers={(DOMAIN, station_id)}
            )
            device_name = (device.name_by_user or device.name) if device else None
            if device_name and device and not device.name_by_user:
                suffix = f" - {station_id}"
                if device_name.endswith(suffix):
                    device_name = device_name[: -len(suffix)]

            station_options[station_id] = (
                f"{device_name} ({station_id})" if device_name else station_id
            )

        if user_input is not None:
            removed_stations = user_input.get("stations_to_remove", [])
            if not removed_stations:
                errors["base"] = "no_stations_selected"
            else:
                remaining_stations = [
                    station_id
                    for station_id in current_stations
                    if station_id not in removed_stations
                ]
                self.hass.config_entries.async_update_entry(
                    self.config_entry,
                    data={
                        **self.config_entry.data,
                        CONF_STATIONS: remaining_stations,
                    },
                )
                return self.async_create_entry(title="", data={})

        return self.async_show_form(
            step_id="remove_stations",
            data_schema=vol.Schema(
                {
                    vol.Optional("stations_to_remove", default=[]): cv.multi_select(
                        station_options
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_add_searched_stations(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Add selected search results without replacing existing stations."""
        errors: dict[str, str] = {}

        if user_input is not None:
            selected_stations = user_input.get(CONF_STATIONS, [])
            self._selected_search_stations = selected_stations
            existing_stations = list(self.config_entry.data.get(CONF_STATIONS, []))
            new_stations = [
                station_id
                for station_id in selected_stations
                if station_id not in existing_stations
            ]

            if not selected_stations:
                errors["base"] = "no_stations_selected"
            elif not new_stations:
                errors["base"] = "already_added"
            else:
                try:
                    for station_id in new_stations:
                        await validate_station(self.hass, station_id)
                    self.hass.config_entries.async_update_entry(
                        self.config_entry,
                        data={
                            **self.config_entry.data,
                            CONF_STATIONS: existing_stations + new_stations,
                        },
                    )
                    return self.async_create_entry(title="", data={})
                except CannotConnect:
                    errors["base"] = "cannot_connect"
                except InvalidStation:
                    errors["base"] = "station_unavailable"

        return self.async_show_form(
            step_id="add_searched_stations",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_STATIONS,
                        default=getattr(self, "_selected_search_stations", []),
                    ): cv.multi_select(self._station_options),
                }
            ),
            errors=errors,
        )

    async def async_step_set_scan_interval(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Set how often the station data is refreshed."""
        errors: dict[str, str] = {}
        current_scan_interval = self.config_entry.data.get(
            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
        )
        try:
            current_scan_interval = int(current_scan_interval)
        except (TypeError, ValueError):
            current_scan_interval = DEFAULT_SCAN_INTERVAL
        if current_scan_interval not in SCAN_INTERVAL_OPTIONS:
            current_scan_interval = DEFAULT_SCAN_INTERVAL

        if user_input is not None:
            self.hass.config_entries.async_update_entry(
                self.config_entry,
                data={
                    **self.config_entry.data,
                    CONF_SCAN_INTERVAL: int(user_input[CONF_SCAN_INTERVAL]),
                },
            )
            return self.async_create_entry(title="", data={})

        return self.async_show_form(
            step_id="set_scan_interval",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SCAN_INTERVAL,
                        default=str(current_scan_interval),
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                selector.SelectOptionDict(
                                    value=str(interval), label=label
                                )
                                for interval, label in SCAN_INTERVAL_OPTIONS.items()
                            ],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                }
            ),
            errors=errors,
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidStation(HomeAssistantError):
    """Error to indicate the station ID is invalid."""
