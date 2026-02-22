"""DataUpdateCoordinator for Vigicrues integration."""
from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

import requests

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import VIGICRUES_OBSERVATIONS_API, VIGICRUES_STATION_API
from .utils import lambert93_to_wgs84

_LOGGER = logging.getLogger(__name__)


class VigicruesDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Class to manage fetching Vigicrues data."""

    def __init__(self, hass: HomeAssistant, station_id: str) -> None:
        """Initialize the coordinator."""
        self.station_id = station_id
        self.station_name: str | None = None
        self.coordinates: tuple[float, float] | None = None

        super().__init__(
            hass,
            _LOGGER,
            name=f"Vigicrues {station_id}",
            update_interval=timedelta(minutes=30),
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from Vigicrues API."""
        try:
            # Fetch station info if not already done
            if self.station_name is None:
                await self._async_fetch_station_info()

            # Fetch observations data
            height = await self._async_fetch_observation("H")
            waterflowrate = await self._async_fetch_observation("Q")

            return {
                "height": height,
                "waterflowrate": waterflowrate,
                "station_name": self.station_name,
                "coordinates": self.coordinates,
            }
        except Exception as err:
            raise UpdateFailed(f"Error communicating with Vigicrues API: {err}") from err

    async def _async_fetch_station_info(self) -> None:
        """Fetch station information from Vigicrues API."""
        params = {"CdStationHydro": self.station_id, "GrdSerie": "H"}

        try:
            response = await self.hass.async_add_executor_job(
                lambda: requests.get(
                    VIGICRUES_OBSERVATIONS_API, params=params, timeout=10
                )
            )
            response.raise_for_status()
            data = response.json()

            serie_data = data.get("Serie", {})
            self.station_name = (
                f"{serie_data.get('LbStationHydro')} - {serie_data.get('CdStationHydro')}"
            )

            # Get coordinates
            coord_response = await self.hass.async_add_executor_job(
                lambda: requests.get(
                    VIGICRUES_STATION_API,
                    params={"CdStationHydro": self.station_id},
                    timeout=10,
                )
            )
            coord_response.raise_for_status()
            coord_data = coord_response.json()

            coordstation = coord_data.get("CoordStationHydro", {})
            coordx = int(coordstation.get("CoordXStationHydro", 0))
            coordy = int(coordstation.get("CoordYStationHydro", 0))

            # Coordinate transformation
            latitude, longitude = lambert93_to_wgs84(coordx, coordy)
            self.coordinates = (longitude, latitude)

        except requests.exceptions.RequestException as err:
            _LOGGER.error(
                "Error fetching station info for %s: %s", self.station_id, err
            )
            raise

    async def _async_fetch_observation(self, observation_type: str) -> float | None:
        """Fetch observation data from Vigicrues API."""
        params = {"CdStationHydro": self.station_id, "GrdSerie": observation_type}

        try:
            response = await self.hass.async_add_executor_job(
                lambda: requests.get(
                    VIGICRUES_OBSERVATIONS_API, params=params, timeout=10
                )
            )
            response.raise_for_status()
            data = response.json()

            obss_hydro = data.get("Serie", {}).get("ObssHydro", [])
            if obss_hydro:
                return obss_hydro[-1].get("ResObsHydro")

            return None
        except requests.exceptions.RequestException as err:
            _LOGGER.warning(
                "Error fetching %s observation for %s: %s",
                observation_type,
                self.station_id,
                err,
            )
            return None
