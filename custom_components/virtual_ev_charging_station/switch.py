from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from .const import DOMAIN

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    async_add_entities([
        EVSolarModeSwitch(entry),
        EVGridModeSwitch(entry)
    ])

class EVBaseSwitch(SwitchEntity):
    _attr_has_entity_name = True

    def __init__(self, entry: ConfigEntry):
        self.entry = entry
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Virtual EV Charging Station",
            manufacturer="Kiko DIY",
            model="Virtual EV Charger",
        )

class EVSolarModeSwitch(EVBaseSwitch):
    _attr_name = "Modo Automático Solar"
    _attr_icon = "mdi:solar-power"

    def __init__(self, entry):
        super().__init__(entry)
        self._attr_unique_id = f"{entry.entry_id}_solar_mode"
        self.entity_id = f"switch.{DOMAIN}_modo_automatico_solar"
        self._attr_is_on = False

    async def async_turn_on(self, **kwargs):
        self._attr_is_on = True
        self.async_write_ha_state()
        self.hass.bus.async_fire(f"{DOMAIN}_update_sensors")

    async def async_turn_off(self, **kwargs):
        self._attr_is_on = False
        self.async_write_ha_state()
        self.hass.bus.async_fire(f"{DOMAIN}_update_sensors")

class EVGridModeSwitch(EVBaseSwitch):
    _attr_name = "Forzar Carga Red"
    _attr_icon = "mdi:transmission-tower"

    def __init__(self, entry):
        super().__init__(entry)
        self._attr_unique_id = f"{entry.entry_id}_grid_mode"
        self.entity_id = f"switch.{DOMAIN}_forzar_carga_red"
        self._attr_is_on = False

    async def async_turn_on(self, **kwargs):
        self._attr_is_on = True
        self.async_write_ha_state()
        self.hass.bus.async_fire(f"{DOMAIN}_update_sensors")

    async def async_turn_off(self, **kwargs):
        self._attr_is_on = False
        self.async_write_ha_state()
        self.hass.bus.async_fire(f"{DOMAIN}_update_sensors")
