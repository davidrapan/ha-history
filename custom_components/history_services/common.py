from __future__ import annotations

import logging

from pathlib import Path
from datetime import datetime as dt

from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse, callback, valid_entity_id
from homeassistant.components.recorder import history
from homeassistant.util import dt as dt_util

from .const import *

_LOGGER = logging.getLogger(__name__)

def open_file(filepath, mode, x):
    file_path = Path(filepath)
    file_path.parent.mkdir(exist_ok = True, parents = True)
    with open(filepath, mode) as file:
        return x(file)

def get_significant_states(hass: HomeAssistant, call: ServiceCall):
    now = dt_util.utcnow()
    start_time = now - ONE_DAY
    end_time = now

    entity_id = call.data["entity_id"]
    entity_ids = list([entity_id])

    if "start" in call.data:
        start_time = dt_util.as_utc(call.data["start"])

    if "end" in call.data:
        end_time = dt_util.as_utc(call.data["end"])

    start_time_local = dt_util.as_local(start_time).isoformat()
    end_time_local = dt_util.as_local(end_time).isoformat()
    timespan = { "start": start_time_local, "end": end_time_local }

    if start_time > now:
        return { "timespan": timespan, "result": "error", "message": "Invalid date" }

    include_start_time_state = True
    significant_changes_only = True
    minimal_response = False
    no_attributes = False

    response = history.get_significant_states(
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

    if not response:
        return { "timespan": timespan, "result": "", "message": "Request returned empty response" }

    result = response[entity_id]
    result.sort(key = lambda i: i.last_updated)

    return { "timespan": timespan, "result": result }
