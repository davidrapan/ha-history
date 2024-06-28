from __future__ import annotations

import logging

from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse, callback

from ..const import *
from ..common import *

_LOGGER = logging.getLogger(__name__)

async def async_register_service(hass: HomeAssistant):
    @callback
    async def export_service(call: ServiceCall) -> ServiceResponse:
        response = get_significant_states(hass, call)

        if not response["result"]:
            return response

        return { "timespan": response["timespan"], "result": [item.as_dict() for item in response["result"]] }

    hass.services.async_register(DOMAIN, EXPORT_SERVICE_NAME, export_service, schema = SERVICE_SCHEMA, supports_response = SupportsResponse.OPTIONAL)
