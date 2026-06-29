import logging
from homeassistant.components.number import RestoreNumber, NumberMode
from .const import DOMAIN, CONF_POTENCIA_CARGA, CONF_UMBRAL_SOLAR

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([
        EVNumber(entry, "porcentaje_actual", "Estado de la Batería", "%", 0.0, 100.0, 50.0, "mdi:battery-50", 1.0),
        EVNumber(entry, "potencia_carga", "Potencia de Carga", "kW", 0.1, 11.0, float(entry.data.get(CONF_POTENCIA_CARGA, 1.5)), "mdi:ev-plug-type2", 0.1),
        EVNumber(entry, "umbral_potencia_solar", "Umbral Producción Solar", "W", 0.0, 10000.0, float(entry.data.get(CONF_UMBRAL_SOLAR, 3000.0)), "mdi:white-balance-sunny", 100.0)
    ])

class EVNumber(RestoreNumber):
    def __init__(self, entry, id_name, display_name, uom, min_v, max_v, default, icon, step):
        self.entity_id = f"number.{DOMAIN}_{id_name}"
        self._attr_name = display_name
        self._attr_unique_id = f"{entry.entry_id}_{id_name}"
        self._attr_native_unit_of_measurement = uom
        self._attr_icon = icon
        self._attr_mode = NumberMode.SLIDER
        
        # Variables internas blindadas para evitar que HA use sus defaults
        self._my_min = float(min_v)
        self._my_max = float(max_v)
        self._my_step = float(step)
        
        self._id_name = id_name
        self._default = float(default)
        self._attr_native_value = self._default

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        last_data = await self.async_get_last_number_data()
        if last_data and last_data.native_value is not None:
            self._attr_native_value = float(last_data.native_value)
        else:
            self._attr_native_value = self._default
        self.async_write_ha_state()

    # === LA CLAVE: Forzamos a Home Assistant a leer nuestras reglas, no su caché ===
    @property
    def native_min_value(self) -> float:
        return self._my_min

    @property
    def native_max_value(self) -> float:
        return self._my_max

    @property
    def native_step(self) -> float:
        return self._my_step

    @property
    def native_value(self) -> float:
        return float(self._attr_native_value) if self._attr_native_value is not None else self._default

    async def async_set_native_value(self, value: float) -> None:
        # Aseguramos un redondeo limpio antes de pasarlo al motor principal
        if self._my_step == 0.1:
            val = round(float(value), 1)
        else:
            val = float(value)
            
        self._attr_native_value = val
        self.async_write_ha_state()
        self.hass.bus.async_fire("virtual_ev_recalc")