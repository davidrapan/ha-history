from __future__ import annotations

import copy
import math
import logging
import asyncio
import aiofiles
import simplekml
import voluptuous as vol

from datetime import datetime as dt, timedelta as td
from pathlib import Path

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
    vol.Optional("directory"): cv.string,
    vol.Optional("filename"): cv.string,
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
            return h > 0.019
    return False

def segment_condition2(attributes):
    if is_gps(attributes):
        if "speed" in attributes and int(attributes["speed"]) > 0:
            return True
        elif "distance" in attributes and attributes["distance"] > 0.009:
            return True
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
        response_result = response["result"]

        if not response_result:
            return response

        if not is_gps(response_result[0].attributes):
            return { "timespan": response["timespan"], "result": "error", "message": "Entity is not a gps tracker" }

        result = []
        # Why is it necessary to do deepcopy when enriching state?
        # - It messes up the values of those added attributes (duplicates, etc.)
        # - Maybe because of the caching nature of LazyState from recorder?
        for i, p in enumerate(response_result):
            point = copy.deepcopy(p)
            point.attributes["timestamp"] = dt_util.as_local(point.last_updated).isoformat()
            if i > 0:
                point.attributes["distance"] = haversine2(result[i - 1].attributes, point.attributes)
                point.attributes["length"] = timediff(result[i - 1].last_updated, point.last_updated)
            else:
                point.attributes["distance"] = 0
                point.attributes["length"] = 0
            result.append(point)

        min_radius = call.data["min_radius"] / 1000
        max_gap = td(seconds = call.data["max_gap"])

        segments = []
        current_segment = []
        result_last = len(result) - 1
        prevp = None
        for i, p in enumerate(result):
            if segment_condition2(p.attributes):
                if not current_segment and i > 0:
                    current_segment.append(result[i - 1])
                current_segment.append(p)
            else:
                if current_segment:
                    #if i < result_last and haversine2(point.attributes, result[i + 1].attributes) > 0:
                    #    result[i + 1].attributes["distance"] = haversine2(current_segment[-1].attributes, result[i + 1].attributes)
                    #    current_segment.append(result[i + 1])
                    #current_segment[0].attributes["distance"] = 0
                    if len(current_segment) > 1 and not are_coords_within([(c.attributes["latitude"], c.attributes["longitude"]) for c in current_segment], min_radius):
                        segments.append(current_segment)
                    current_segment = []

        connected_segments = []
        current_segment = []
        for i, segment in enumerate(segments):
            if not current_segment or timediff(current_segment[-1].last_updated, segment[0].last_updated) <= max_gap:
            #if not current_segment or point.attributes["length"] <= max_gap:
                segment[0].attributes["distance"] = haversine2(current_segment[-1].attributes, segment[0].attributes) if i > 0 else 0
                segment[0].attributes["length"] = timediff(current_segment[-1].last_updated, segment[0].last_updated) if i > 0 else 0
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
            attributes_list = [i for i in attributes.split() if i in result[0].attributes]
            for item in attributes_list:
                type = simplekml.Types.int if isinstance(result[0].attributes[item], int) else simplekml.Types.string
                schema.newgxsimplearrayfield(name = item, type = type, displayname = item.capitalize())

        for s in connected_segments:
            l = 0
            for p in s:
                l += p.attributes["distance"]
            l = round(l, 3)
            t = s[-1].last_updated - s[0].last_updated
            linestring = kml.newlinestring(name = (str(dt_util.as_local(s[0].last_updated)) + " - " + str(dt_util.as_local(s[-1].last_updated)) + ", duration: " + str(t) + ", length: " + str(l) + " km"))
            linestring.timespan.begin = str(s[0].last_updated)
            linestring.timespan.end = str(s[-1].last_updated)
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

        directory = "www/history/"
        filename = "device_tracker"
        fileext = "kml"
        file = ""

        if "directory" in call.data:
            if call_directory := call.data["directory"]:
                directory = call_directory

        if "filename" in call.data:
            filename = ""
            if call_filename := call.data["filename"]:
                filename = call_filename

        if directory and filename and fileext:
            file = hass.config.path(f'{directory}{filename}.{fileext}')

        if file:
            file_path = Path(file)
            file_path.parent.mkdir(exist_ok = True, parents = True)
            async with aiofiles.open(file, "w") as f:
                await f.write(kml.kml())

        return { "timespan": response["timespan"], "result": kml.kml() }

    #integration = await async_get_integration(hass, "history_services")
    #platform = await integration.async_get_platform("history_services")
    #platform.async_register_entity_service(EXPORT_DEVICE_TRACKER_SERVICE_NAME, export_service, schema = _SERVICE_SCHEMA)

    hass.services.async_register(DOMAIN, EXPORT_DEVICE_TRACKER_SERVICE_NAME, export_service, schema = _SERVICE_SCHEMA, supports_response = SupportsResponse.OPTIONAL)

#async def async_remove_service(hass: HomeAssistant):
#    hass.services.async_remove(DOMAIN, EXPORT_DEVICE_TRACKER_SERVICE_NAME)