from __future__ import annotations

import math
import logging
import asyncio
import simplekml
import voluptuous as vol

from datetime import datetime as dt, timedelta as td

#from homeassistant.loader import async_get_integration
#from homeassistant.helpers.entity_platform import EntityPlatform
#from homeassistant.helpers.entity_component import EntityComponent

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
    vol.Required("max_gap"): int,
    vol.Optional("attributes"): cv.string,
    vol.Optional("filepath"): cv.string,
})

# Haversine formula to calculate the distance between two lat/lon points
def haversine(lat1, lon1, lat2, lon2):
    R = 6371  # Earth radius in kilometers

    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

# Function to remove close points
def remove_close_points(points, threshold_km):
    if not points:
        return []

    filtered_points = [points[0]]
    for point in points[1:]:
        too_close = any(haversine(point[0], point[1], fp[0], fp[1]) < threshold_km for fp in filtered_points)
        if not too_close:
            filtered_points.append(point)
    return filtered_points

def group_when(iterable, predicate):
    i, x, size = 0, 0, len(iterable)
    while i < size - 1:
        if predicate(iterable[i], iterable[i + 1]):
            yield iterable[x:i + 1]
            x = i + 1
        i += 1
    yield iterable[x:size]

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

        max_gap = int(call.data["max_gap"])

        attributes = ""
        if "attributes" in call.data:
            attributes = call.data["attributes"]

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

        #loop = asyncio.get_running_loop()
        #await loop.run_in_executor(None, lambda: open_file(hass.config.path(f'www/export/history_data.txt'), "w", 
        #    lambda file: file.write(str(entity_result))))

        #threshold_km = 0.1  # Set threshold distance
        #linestring_coords = [(p.attributes["longitude"], p.attributes["latitude"], p.attributes["altitude"]) for p in entity_result]
        #linestring.coords = remove_close_points(linestring_coords, threshold_km)

        segments = []
        current_segment = []
        for i, point in enumerate(entity_result):
            point.attributes["timestamp"] = dt_util.as_local(point.last_changed).isoformat()

            p_attr = point.attributes
            if (int(p_attr['speed']) > 0.1 or (len(current_segment) > 0 and haversine(p_attr["latitude"], p_attr["longitude"], current_segment[-1].attributes["latitude"], current_segment[-1].attributes["longitude"]) > 0.05)):
                if len(current_segment) == 0 and i > 0:
                    current_segment.append(entity_result[i - 1])
                current_segment.append(point)
            else:
                if current_segment:
                    segments.append(current_segment)
                    current_segment = []

        connected_segments = []
        current_segment = []
        for i, segment in enumerate(segments):
            if haversine(segment[0].attributes["latitude"], segment[0].attributes["longitude"], segment[-1].attributes["latitude"], segment[-1].attributes["longitude"]) < 0.05:
                continue

            if len(current_segment) == 0 or (segment[0].last_changed - current_segment[-1].last_changed) <= td(seconds = max_gap):
                current_segment.extend(segment)
            else:
                connected_segments.append(current_segment)
                current_segment = segment

        connected_segments.append(current_segment)

        if len(connected_segments) == 0 or len(connected_segments[0]) == 0:
            return { "timespan": { "start": str_start_time, "end": str_end_time }, "result": "", "message": "Request returned empty response" }

        kml = simplekml.Kml(open = 1)

        if attributes:
            schema = kml.newschema()
            attributes_list = [i for i in attributes.split() if i in connected_segments[0][0].attributes]
            for item in attributes_list:
                type = simplekml.Types.int if isinstance(connected_segments[0][0].attributes[item], int) else simplekml.Types.string
                schema.newgxsimplearrayfield(name = item, type = type, displayname = item.capitalize())

        for s in connected_segments:
            linestring = kml.newlinestring(name = (str(dt_util.as_local(s[0].last_changed)) + " - " + str(dt_util.as_local(s[-1].last_changed))))
            linestring.timespan.begin = str(s[0].last_changed)
            linestring.timespan.end = str(s[-1].last_changed)
            linestring.coords = [(p.attributes["longitude"], p.attributes["latitude"], p.attributes["altitude"]) for p in s]
            if attributes:
                linestring.extendeddata.schemadata.schemaurl = schema.id
                for item in attributes_list:
                    linestring.extendeddata.schemadata.newgxsimplearraydata(item, [(p.attributes[item]) for p in s])

        #for s in connected_segments:
        #    folder = kml.newfolder(name = (str(dt_util.as_local(s[0].last_reported)) + " - " + str(dt_util.as_local(s[-1].last_reported))))
        #    for p in list(zip(s, s[1:])):
        #        linestring = folder.newlinestring(name = (str(dt_util.as_local(p[0].last_reported)) + " - " + str(dt_util.as_local(p[1].last_reported))))
        #        linestring.coords = [(p[0].attributes["longitude"], p[0].attributes["latitude"], p[0].attributes["altitude"]), (p[1].attributes["longitude"], p[1].attributes["latitude"], p[1].attributes["altitude"])]
        #        linestring.timespan.begin = str(p[0].last_reported)
        #        linestring.timespan.end = str(p[1].last_reported)

        if "filepath" in call.data:
            if call_filepath := call.data["filepath"]:
                filepath = hass.config.path(call_filepath)
            else:
                filepath = ""
        else:
            filepath = hass.config.path(f'www/history/device_tracker.kml')

        if filepath:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, lambda: open_file(filepath, "w", 
                lambda file: file.write(kml.kml())))

        return { "timespan": { "start": str_start_time, "end": str_end_time }, "result": kml.kml() }

    #integration = await async_get_integration(hass, "history_services")
    #platform = await integration.async_get_platform("history_services")
    #platform.async_register_entity_service(EXPORT_DEVICE_TRACKER_SERVICE_NAME, export_service, schema = _SERVICE_SCHEMA)

    hass.services.async_register(DOMAIN, EXPORT_DEVICE_TRACKER_SERVICE_NAME, export_service, schema = _SERVICE_SCHEMA, supports_response = SupportsResponse.OPTIONAL)

#async def async_remove_service(hass: HomeAssistant):
#    hass.services.async_remove(DOMAIN, EXPORT_DEVICE_TRACKER_SERVICE_NAME)