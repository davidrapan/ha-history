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

from homeassistant.helpers import config_validation as cv
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse, callback
from homeassistant.util import dt as dt_util

from ..const import *
from ..common import *

_LOGGER = logging.getLogger(__name__)

_SERVICE_SCHEMA = SERVICE_SCHEMA
_SERVICE_SCHEMA = _SERVICE_SCHEMA.extend({
    vol.Required("max_gap"): int,
    vol.Required("min_radius"): int,
    vol.Optional("attributes"): cv.string,
    vol.Optional("filepath"): cv.string,
})

def is_gps(attributes):
    return "source_type" in attributes and attributes["source_type"] == "gps"

def haversine(lat1, lon1, lat2, lon2):
    dLat = math.radians(lat2 - lat1)
    dLon = math.radians(lon2 - lon1)
    lat1 = math.radians(lat1)
    lat2 = math.radians(lat2)

    a = math.sin(dLat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dLon / 2) ** 2
    c = 2 * math.asin(math.sqrt(a))

    return EARTH_RADIUS * c

def haversine2(coords1, coords2):
    return haversine(coords1["latitude"], coords1["longitude"], coords2["latitude"], coords2["longitude"])

def timediff(dt1, dt2):
    return dt1 - dt2 if dt1 > dt2 else dt2 - dt1

def segment_condition(attributes1, attributes2):
    if is_gps(attributes1):
        if "speed" in attributes1 and int(attributes1["speed"]) > 0:
            return True
        elif attributes2:
            return haversine2(attributes1, attributes2) > 0.019
    return False

def are_coords_within(points, radius):
    n = len(points)
    for i in range(n):
        for j in range(i + 1, n):
            distance = haversine(points[i][0], points[i][1], points[j][0], points[j][1])
            if distance > radius:
                return False
    return True

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
        response = get_significant_states(hass, call)
        result = response["result"]

        if not result:
            return response

        if not is_gps(result[0].attributes):
            return { "timespan": response["timespan"], "result": "error", "message": "Entity is not a gps tracker" }

        segments = []
        current_segment = []
        result_last = len(result) - 1
        for i, point in enumerate(result):
            point.attributes["timestamp"] = dt_util.as_local(point.last_changed).isoformat()
            if segment_condition(point.attributes, result[i + 1].attributes if i < result_last else []):
                if current_segment and i > 0:
                    current_segment.append(result[i - 1])
                current_segment.append(point)
            else:
                if current_segment:
                    if len(current_segment) > 1 and i < result_last:
                        current_segment.append(result[i + 1])
                    segments.append(current_segment)
                    current_segment = []

        min_radius = call.data["min_radius"] / 1000
        max_gap = td(seconds = call.data["max_gap"])

        connected_segments = []
        current_segment = []
        for i, segment in enumerate(segments):
            if are_coords_within([(c.attributes["latitude"], c.attributes["longitude"]) for c in segment], min_radius):
                continue

            if not current_segment or timediff(segment[0].last_changed, current_segment[-1].last_changed) <= max_gap:
                current_segment.extend(segment)
            else:
                connected_segments.append(current_segment)
                current_segment = segment

        connected_segments.append(current_segment)

        if not connected_segments or not connected_segments[0]:
            return { "timespan": response["timespan"], "result": "", "message": "Request returned empty response" }

        kml = simplekml.Kml(open = 1)

        attributes = ""
        if "attributes" in call.data:
            attributes = call.data["attributes"]

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

        return { "timespan": response["timespan"], "result": kml.kml() }

    #integration = await async_get_integration(hass, "history_services")
    #platform = await integration.async_get_platform("history_services")
    #platform.async_register_entity_service(EXPORT_DEVICE_TRACKER_SERVICE_NAME, export_service, schema = _SERVICE_SCHEMA)

    hass.services.async_register(DOMAIN, EXPORT_DEVICE_TRACKER_SERVICE_NAME, export_service, schema = _SERVICE_SCHEMA, supports_response = SupportsResponse.OPTIONAL)

#async def async_remove_service(hass: HomeAssistant):
#    hass.services.async_remove(DOMAIN, EXPORT_DEVICE_TRACKER_SERVICE_NAME)