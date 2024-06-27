from __future__ import annotations

import math
import logging
import asyncio
import simplekml

from datetime import datetime as dt, timedelta as td

from homeassistant.helpers.entity import Entity
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse, callback, valid_entity_id
from homeassistant.components.recorder import history
from homeassistant.util import dt as dt_util

from ..const import *
from ..common import *

_LOGGER = logging.getLogger(__name__)

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

        start_time_local = dt_util.as_local(start_time).isoformat()
        end_time_local = dt_util.as_local(end_time).isoformat()

        if start_time > now:
            return { "timespan": { "start": start_time_local, "end": end_time_local }, "result": "error", "message": "Invalid date" }

        include_start_time_state = True
        significant_changes_only = True
        minimal_response = False
        no_attributes = False

        results = history.get_significant_states(
            hass,
            start_time,
            end_time,
            entity_ids,
            None,
            include_start_time_state,
            significant_changes_only,
            minimal_response,
            no_attributes,
        )

        result = results[call.data["entity_id"]]

        return { "timespan": { "start": start_time_local, "end": end_time_local }, "result": [item.as_dict() for item in result] }

    hass.services.async_register(DOMAIN, EXPORT_SERVICE_NAME, export_service, schema = SERVICE_SCHEMA, supports_response = SupportsResponse.OPTIONAL)
