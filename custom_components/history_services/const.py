import voluptuous as vol

from datetime import timedelta as td

from homeassistant.helpers import config_validation as cv

DOMAIN = "history_services"

EXPORT_SERVICE_NAME = "export"
EXPORT_DEVICE_TRACKER_SERVICE_NAME = "export_device_tracker"

SERVICE_SCHEMA = vol.Schema({
    vol.Required("entity_id"): cv.entity_id,
    vol.Optional("start"): cv.datetime,
    vol.Optional("end"): cv.datetime,
})

ONE_DAY = td(days = 1)

EARTH_RADIUS = 6372.8 # Earth radius in kilometers
