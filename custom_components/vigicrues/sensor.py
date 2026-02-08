"""Platform for vigicrues sensor integration."""
from datetime import timedelta
import logging
import requests
import voluptuous as vol

from homeassistant.components.sensor import PLATFORM_SCHEMA, SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_LATITUDE, ATTR_LONGITUDE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
import homeassistant.helpers.config_validation as cv
from homeassistant.util import slugify

from .const import CONF_STATIONS, DOMAIN, VIGICRUES_OBSERVATIONS_API, VIGICRUES_STATION_API, METRICS_INFO, VIGICRUES_PICTURE
from .coordinator import VigicruesDataUpdateCoordinator
from .utils import lambert93_to_wgs84

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(minutes=30)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {vol.Required(CONF_STATIONS): vol.All(cv.ensure_list, [cv.string])}
)


def setup_platform(hass, config, add_entities, discovery_info=None):
    """Set up the sensor."""

    sensors = []
    for station_id in config.get(CONF_STATIONS):
        station = Vigicrues(station_id)
        station.update()
        sensors.append(VigicruesHeightSensor(station))
        sensors.append(VigicruesWaterFlowRateSensor(station))

    add_entities(sensors, True)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Vigicrues sensors from a config entry."""
    coordinators: dict[str, VigicruesDataUpdateCoordinator] = hass.data[DOMAIN][
        config_entry.entry_id
    ]

    entities = []
    for station_id, coordinator in coordinators.items():
        entities.append(VigicruesCoordinatorHeightSensor(coordinator))
        entities.append(VigicruesCoordinatorWaterFlowRateSensor(coordinator))

    async_add_entities(entities)


class VigicruesSensor(Entity):
    """Representation of a Vigicrues Sensor."""

    def __init__(self, station, _type):
        """Initialize the sensor."""
        self.station = station
        self._type = _type
        self._attr_extra_state_attributes = {
            ATTR_LONGITUDE: self.station.coordinates[0],
            ATTR_LATITUDE: self.station.coordinates[1],
            "LbStationHydro": self.station.LbStationHydro,
            "CdCommune": self.station.CdCommune,
            "LbCoursEau": self.station.LbCoursEau,
            "station_id": self.station.station_id,
            "type": self._type,
            "friendly_name": f"Vigicrues {self.station.LbStationHydro} {self.station.station_id} {self.name_type()}"
        }
        self._attr_unique_id = slugify(f"{self.station.station_id}_{self._type}")
        self._attr_entity_picture = station.get_entity_picture()

    def name_type(self):
        """Return the name of the type."""
        return METRICS_INFO.get(self._type).get("name")

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return METRICS_INFO.get(self._type).get("unit")


class VigicruesHeightSensor(VigicruesSensor):
    """Representation of Vigicrues Height Sensor."""

    _attr_device_class = SensorDeviceClass.DISTANCE
    _attr_icon = "mdi:waves-arrow-up"

    def __init__(self, station):
        """Initialize the sensor."""
        super().__init__(station, "H")
        self._state = self.station.height

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    def update(self):
        """Fetch new state data for the sensor."""
        self.station.update()
        self._state = self.station.height


class VigicruesWaterFlowRateSensor(VigicruesSensor):
    """Representation of Vigicrues WaterFlow Sensor."""

    _attr_device_class = SensorDeviceClass.VOLUME_FLOW_RATE
    _attr_icon = "mdi:waves"

    def __init__(self, station):
        """Initialize the sensor."""
        super().__init__(station, "Q")
        self._state = self.station.waterflowrate

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    def update(self):
        """Fetch new state data for the sensor."""
        self.station.update()
        self._state = self.station.waterflowrate


class Vigicrues(object):
    """vigicrues object."""

    def __init__(self, station_id):
        """Initialize"""
        self.station_id = station_id
        station_info = self.get_station()
        self.LbStationHydro = station_info.get("LbStationHydro")
        self.CdCommune = station_info.get("CdCommune")
        self.LbCoursEau = station_info.get("LbCoursEau")
        self.waterflowrate = None
        self.height = None
        self.coordinates = self.get_coordinates()

    def get_station(self):
        """ Get Station info from VIGICRUE """
        params = {"CdStationHydro": self.station_id}

        try:
            data = requests.get(VIGICRUES_STATION_API, params=params, timeout=10)
            data.raise_for_status()
        except Exception:
            _LOGGER.error("Unable to get data from %s", VIGICRUES_STATION_API)
            raise Exception("Unable to get data")

        return data.json()

    def get_height(self):
        return self.__get_last_point("H")

    def get_waterflowrate(self):
        return self.__get_last_point("Q")

    def get_observations(self, _type):
        """ Get Station's Observations from VIGICRUE """
        params = {"CdStationHydro": self.station_id, "GrdSerie": _type}

        try:
            data = requests.get(VIGICRUES_OBSERVATIONS_API, params=params, timeout=10)
            data.raise_for_status()
        except Exception:
            _LOGGER.exception("Unable to get observations from %s", VIGICRUES_OBSERVATIONS_API)
            raise Exception("Unable to get observations")

        return data.json()

    def get_coordinates(self):
        """ Get coordinates from VIGICRUE and transform them in longitude and latitute """

        coordstation = self.get_station().get("CoordStationHydro")
        coordx, coordy = coordstation.get("CoordXStationHydro"), coordstation.get("CoordYStationHydro")

        # Coordinate transformation
        latitude, longitude = lambert93_to_wgs84(int(coordx), int(coordy))

        return (longitude, latitude)

    def get_entity_picture(self):
        """ Get Entity picture from VIGICRUE """
        url_picture = f"{VIGICRUES_PICTURE}/photo_{self.station_id}.jpg"
        try:
            response = requests.get(url_picture, timeout=10)
            response.raise_for_status()
        except Exception:
            return ""
        else:
            return url_picture

    def __get_last_point(self, _type):
        """ Get last metric point """
        try:
            return self.get_observations(_type)["Serie"]["ObssHydro"][-1]["ResObsHydro"]
        except Exception:
            return

    def update(self):
        self.waterflowrate = self.get_waterflowrate()
        self.height = self.get_height()


class VigicruesCoordinatorHeightSensor(CoordinatorEntity, SensorEntity):
    """Representation of Vigicrues Height Sensor using coordinator."""

    _attr_device_class = SensorDeviceClass.DISTANCE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:waves-arrow-up"
    _attr_translation_key = "height"

    def __init__(self, coordinator: VigicruesDataUpdateCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = slugify(f"{coordinator.station_id}_H")
        self._attr_has_entity_name = True

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information about this sensor."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.station_id)},
            name=self.coordinator.data.get("station_name", f"Station {self.coordinator.station_id}"),
            manufacturer="Vigicrues",
            model="Station hydrométrique",
            configuration_url=f"https://www.vigicrues.gouv.fr/station/{self.coordinator.station_id}",
        )

    @property
    def native_value(self):
        """Return the state of the sensor."""
        return self.coordinator.data.get("height")

    @property
    def native_unit_of_measurement(self):
        """Return the unit of measurement."""
        return METRICS_INFO.get("H").get("unit")

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        coordinates = self.coordinator.data.get("coordinates", (None, None))
        return {
            ATTR_LONGITUDE: coordinates[0],
            ATTR_LATITUDE: coordinates[1],
            "station_id": self.coordinator.station_id,
            "type": "H",
        }


class VigicruesCoordinatorWaterFlowRateSensor(CoordinatorEntity, SensorEntity):
    """Representation of Vigicrues WaterFlow Sensor using coordinator."""

    _attr_device_class = SensorDeviceClass.VOLUME_FLOW_RATE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:waves"
    _attr_translation_key = "waterflowrate"

    def __init__(self, coordinator: VigicruesDataUpdateCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = slugify(f"{coordinator.station_id}_Q")
        self._attr_has_entity_name = True

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information about this sensor."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.station_id)},
            name=self.coordinator.data.get("station_name", f"Station {self.coordinator.station_id}"),
            manufacturer="Vigicrues",
            model="Station hydrométrique",
            configuration_url=f"https://www.vigicrues.gouv.fr/station/{self.coordinator.station_id}",
        )

    @property
    def native_value(self):
        """Return the state of the sensor."""
        return self.coordinator.data.get("waterflowrate")

    @property
    def native_unit_of_measurement(self):
        """Return the unit of measurement."""
        return METRICS_INFO.get("Q").get("unit")

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        coordinates = self.coordinator.data.get("coordinates", (None, None))
        return {
            ATTR_LONGITUDE: coordinates[0],
            ATTR_LATITUDE: coordinates[1],
            "station_id": self.coordinator.station_id,
            "type": "Q",
        }
