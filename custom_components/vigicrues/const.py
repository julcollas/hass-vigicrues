from homeassistant.const import UnitOfLength

DOMAIN = "vigicrues"
CONF_STATIONS = "stations"
CONF_SCAN_INTERVAL = "scan_interval"
DEFAULT_SCAN_INTERVAL = 15
SCAN_INTERVAL_OPTIONS = {15: "15 minutes", 30: "30 minutes", 60: "60 minutes"}
VIGICRUES_URL = "https://www.vigicrues.gouv.fr"
VIGICRUES_PICTURE = f"{VIGICRUES_URL}/ftp/niv3/photos"
VIGICRUES_OBSERVATIONS_API = f"{VIGICRUES_URL}/services/observations.json/index.php"
VIGICRUES_STATION_API = f"{VIGICRUES_URL}/services/station.json/index.php"

METRICS_INFO = {
    "H": {"name": "Hauteur", "unit": UnitOfLength.METERS},
    "Q": {"name": "Debit", "unit": "m³/s"},
}
