from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    async_add_entities([
        EVSolarModeSwitch(entry),
        EVGridModeSwitch(entry)
    ])

class EVSolarModeSwitch(SwitchEntity):
    _attr_has_entity_name = True
    _attr_name = "Modo Automático Solar"
    _attr_icon = "mdi:solar-power"

    def __init__(self, entry):
        self._attr_unique_id = f"{entry.entry_id}_solar_mode"
        self._attr_is_on = False

    async def async_turn_on(self, **kwargs):
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs):
        self._attr_is_on = False
        self.async_write_ha_state()

class EVGridModeSwitch(SwitchEntity):
    _attr_has_entity_name = True
    _attr_name = "Forzar Carga Red"
    _attr_icon = "mdi:transmission-tower"

    def __init__(self, entry):
        self._attr_unique_id = f"{entry.entry_id}_grid_mode"
        self._attr_is_on = False

    async def async_turn_on(self, **kwargs):
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs):
        self._attr_is_on = False
        self.async_write_ha_state()
