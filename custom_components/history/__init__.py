from __future__ import annotations

import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType
from homeassistant.config_entries import ConfigEntry

from .services.export import async_register_service as async_register_export_service
from .services.device_tracker import async_register_service as async_register_device_tracker_service

_LOGGER = logging.getLogger(__name__)

async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    _LOGGER.debug(f'async_setup({config})')
    await async_register_export_service(hass)
    await async_register_device_tracker_service(hass)
    return True

#async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
#    _LOGGER.debug(f'async_setup_entry({entry.as_dict()})')
#    await async_register_services(hass)
#    return True

#async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
#    _LOGGER.debug(f'async_unload_entry({entry.as_dict()})')
#    await async_remove_services(hass)
#    return True