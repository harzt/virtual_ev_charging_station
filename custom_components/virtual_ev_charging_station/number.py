from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from .const import DOMAIN, CONF_POTENCIA_CARGA, CONF_UMBRAL_SOLAR

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    async_add_entities([
        EVBatteryNumber(entry),
        EVChargingPowerNumber(entry),
        EVSolarThresholdNumber(entry)
    ])

class EVBatteryNumber(NumberEntity):
    _attr_has_entity_name = True
    _attr_name = "Porcentaje Actual"
    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_icon = "mdi:battery-charging"

    def __init__(self, entry):
        self._attr_unique_id = f"{entry.entry_id}_battery_percent"
        self._attr_native_value = 20
        self.entry = entry

    async def async_set_native_value(self, value: float) -> None:
        self._attr_native_value = value
        self.async_write_ha_state()
        self.hass.bus.async_fire(f"{DOMAIN}_update_sensors")

class EVChargingPowerNumber(NumberEntity):
    _attr_has_entity_name = True
    _attr_name = "Potencia de Carga"
    _attr_native_min_value = 0.1
    _attr_native_max_value = 11.0
    _attr_native_step = 0.1
    _attr_icon = "mdi:ev-plug-type2"
    _attr_native_unit_of_measurement = "kW"

    def __init__(self, entry):
        self._attr_unique_id = f"{entry.entry_id}_charging_power"
        self._attr_native_value = entry.data.get(CONF_POTENCIA_CARGA, 1.4)
        self.entry = entry

    async def async_set_native_value(self, value: float) -> None:
        self._attr_native_value = value
        self.async_write_ha_state()
        self.hass.bus.async_fire(f"{DOMAIN}_update_sensors")

class EVSolarThresholdNumber(NumberEntity):
    _attr_has_entity_name = True
    _attr_name = "Umbral Potencia Solar"
    _attr_native_min_value = 0
    _attr_native_max_value = 10000
    _attr_native_step = 100
    _attr_icon = "mdi:white-balance-sunny"
    _attr_native_unit_of_measurement = "W"

    def __init__(self, entry):
        self._attr_unique_id = f"{entry.entry_id}_solar_threshold"
        self._attr_native_value = entry.data.get(CONF_UMBRAL_SOLAR, 3000.0)
        self.entry = entry

    async def async_set_native_value(self, value: float) -> None:
        self._attr_native_value = value
        self.async_write_ha_state()
