import logging
from datetime import time as dt_time
from homeassistant.components.time import TimeEntity
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([
        EVTime(entry, "hora_inicio", "Hora de Inicio Programada", dt_time(22, 0, 0), "mdi:clock-start")
    ])

class EVTime(TimeEntity):
    def __init__(self, entry, id_name, display_name, default_time, icon):
        self.entity_id = f"time.{DOMAIN}_{id_name}"
        self._attr_name = display_name
        self._attr_unique_id = f"{entry.entry_id}_{id_name}"
        self._attr_icon = icon
        self._attr_native_value = default_time

    async def async_set_value(self, value: dt_time) -> None:
        self._attr_native_value = value
        self.async_write_ha_state()
        self.hass.bus.async_fire("virtual_ev_recalc")