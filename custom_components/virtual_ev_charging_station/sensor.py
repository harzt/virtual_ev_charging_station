from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.entity import DeviceInfo
from .const import DOMAIN, CONF_CAPACIDAD, CONF_POTENCIA_CARGA, CONF_ENERGIA

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    kwh_sensor = EVKwhRemainingSensor(entry)
    time_sensor = EVTimeRemainingSensor(entry, kwh_sensor)
    corte_sensor = EVTargetEnergySensor(entry, hass)
    
    async_add_entities([kwh_sensor, time_sensor, corte_sensor])
    hass.data[DOMAIN][entry.entry_id]["sensor_corte"] = corte_sensor

class EVBaseSensor(SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, entry: ConfigEntry):
        self.entry = entry
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Virtual EV Charging Station",
            manufacturer="Kiko DIY",
            model="Virtual EV Charger",
        )

class EVKwhRemainingSensor(EVBaseSensor):
    _attr_name = "Energía Restante (80%)"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = "kWh"
    _attr_icon = "mdi:lightning-bolt"

    def __init__(self, entry):
        super().__init__(entry)
        self._attr_unique_id = f"{entry.entry_id}_kwh_remaining"
        self.entity_id = f"sensor.{DOMAIN}_energia_restante_80"
        self._attr_native_value = 0.0

    async def async_added_to_hass(self):
        self.hass.bus.async_listen(f"{DOMAIN}_update_sensors", self._update_calc)
        self._update_calc()

    @callback
    def _update_calc(self, event=None):
        entry_id = self.entry.entry_id
        data = self.hass.data[DOMAIN].get(entry_id, {})
        corte = data.get("energia_corte", 0.0)
        
        if corte > 0.0:
            conf_energia = self.entry.data.get(CONF_ENERGIA)
            energy_state = self.hass.states.get(conf_energia)
            current_energy = float(energy_state.state) if energy_state and energy_state.state not in ["unknown", "unavailable"] else 0.0
            self._attr_native_value = max(0.0, round(corte - current_energy, 2))
        else:
            pct_state = self.hass.states.get(f"number.{DOMAIN}_porcentaje_actual")
            if pct_state and pct_state.state not in ['unknown', 'unavailable']:
                actual = float(pct_state.state)
                capacidad = self.entry.data.get(CONF_CAPACIDAD, 13.0)
                eficiencia = 0.88
                objetivo = 80.0
                
                if actual < objetivo:
                    val = (((objetivo - actual) / 100) * capacidad) / eficiencia
                    self._attr_native_value = round(val, 2)
                else:
                    self._attr_native_value = 0.0
            else:
                self._attr_native_value = 0.0
        self.async_write_ha_state()

class EVTimeRemainingSensor(EVBaseSensor):
    _attr_name = "Tiempo Restante"
    _attr_icon = "mdi:clock-charging-outline"

    def __init__(self, entry, kwh_sensor):
        super().__init__(entry)
        self._attr_unique_id = f"{entry.entry_id}_time_remaining"
        self.entity_id = f"sensor.{DOMAIN}_tiempo_restante"
        self.kwh_sensor = kwh_sensor
        self._attr_native_value = "0m"

    async def async_added_to_hass(self):
        self.hass.bus.async_listen(f"{DOMAIN}_update_sensors", self._update_calc)
        self._update_calc()

    @callback
    def _update_calc(self, event=None):
        kwh = self.kwh_sensor.native_value
        
        power_state = self.hass.states.get(f"number.{DOMAIN}_potencia_de_carga")
        if power_state and power_state.state not in ['unknown', 'unavailable']:
            potencia = float(power_state.state)
        else:
            potencia = self.entry.data.get(CONF_POTENCIA_CARGA, 1.4)
        
        if kwh and kwh > 0 and potencia > 0:
            horas_totales = kwh / potencia
            horas = int(horas_totales)
            minutos = round((horas_totales - horas) * 60)
            self._attr_native_value = f"{horas}h {minutos}m" if horas > 0 else f"{minutos}m"
        else:
            self._attr_native_value = "0m"
        self.async_write_ha_state()

class EVTargetEnergySensor(RestoreEntity, SensorEntity):
    _attr_has_entity_name = True
    _attr_name = "Energía de Corte"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = "kWh"
    _attr_icon = "mdi:calculator"

    def __init__(self, entry, hass):
        self.entry = entry
        self.hass_obj = hass
        self._attr_unique_id = f"{entry.entry_id}_kwh_cutoff"
        self.entity_id = f"sensor.{DOMAIN}_energia_de_corte"
        self._attr_native_value = 0.0
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Virtual EV Charging Station",
            manufacturer="Kiko DIY",
            model="Virtual EV Charger",
        )

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        state = await self.async_get_last_state()
        if state and state.state not in ["unknown", "unavailable"]:
            val = float(state.state)
            self._attr_native_value = val
            self.hass_obj.data[DOMAIN][self.entry.entry_id]["energia_corte"] = val

    def update_value(self, value: float):
        self._attr_native_value = round(value, 2)
        self.async_write_ha_state()
