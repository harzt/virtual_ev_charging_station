import logging
from homeassistant.components.switch import SwitchEntity
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([
        EVSwitch(entry, "modo_automatico_solar", "Carga Automática Solar", "mdi:solar-power-variant"),
        EVSwitch(entry, "forzar_carga_red", "Forzar Carga desde Red", "mdi:transmission-tower"),
        EVSwitch(entry, "modo_programado", "Carga Programada Horaria", "mdi:clock-outline")
    ])

class EVSwitch(SwitchEntity):
    def __init__(self, entry, id_name, display_name, icon):
        self.entity_id = f"switch.{DOMAIN}_{id_name}"
        self._attr_name = display_name
        self._attr_unique_id = f"{entry.entry_id}_{id_name}"
        self._attr_icon = icon
        self._attr_is_on = False

    @property
    def is_on(self):
        return self._attr_is_on

    async def async_turn_on(self, **kwargs):
        self._attr_is_on = True
        self.async_write_ha_state()
        self.hass.bus.async_fire("virtual_ev_recalc")

    async def async_turn_off(self, **kwargs):
        self._attr_is_on = False
        self.async_write_ha_state()
        self.hass.bus.async_fire("virtual_ev_recalc")