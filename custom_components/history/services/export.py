from __future__ import annotations

import math
import logging
import asyncio
import simplekml
import voluptuous as vol

from datetime import datetime as dt, timedelta as td

from homeassistant.helpers.entity import Entity
from homeassistant.helpers import config_validation as cv
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse, callback, valid_entity_id
from homeassistant.components.recorder import get_instance, history
from homeassistant.components.recorder.util import session_scope
from homeassistant.util import dt as dt_util

from ..const import *
from ..common import *

_LOGGER = logging.getLogger(__name__)

_SERVICE_SCHEMA = vol.Schema({
    vol.Required("entity_id"): cv.entity_id,
    vol.Optional("start"): cv.datetime,
    vol.Optional("end"): cv.datetime,
})

async def async_register_service(hass: HomeAssistant):
    @callback
    async def export_service(call: ServiceCall) -> ServiceResponse:
        now = dt_util.utcnow()
        start_time = now - ONE_DAY
        end_time = now

        entity_ids = list([call.data["entity_id"]])

        if "start" in call.data:
            start_time = dt_util.as_utc(call.data["start"])

        if "end" in call.data:
            end_time = dt_util.as_utc(call.data["end"])

        str_start_time = str(start_time)
        str_end_time = str(end_time)

        if start_time > now:
            return { "timespan": { "start": str_start_time, "end": str_end_time }, "result": "error", "message": "Invalid date" }

        include_start_time_state = True
        significant_changes_only = True
        minimal_response = False
        no_attributes = False

        result = []

        with session_scope(hass = hass, read_only = True) as session:
            result = history.get_significant_states_with_session(
                hass,
                session,
                start_time,
                end_time,
                entity_ids,
                None,
                include_start_time_state,
                significant_changes_only,
                minimal_response,
                no_attributes,
            )

        entity_result = result[call.data["entity_id"]]

        return { "timespan": { "start": str_start_time, "end": str_end_time }, "result": [item.as_dict() for item in entity_result] }

    hass.services.async_register(DOMAIN, EXPORT_SERVICE_NAME, export_service, schema = _SERVICE_SCHEMA, supports_response = SupportsResponse.OPTIONAL)
