from homeassistant.components.number import NumberEntity
from .const import DOMAIN, CONF_POTENCIA_CARGA, CONF_UMBRAL_SOLAR

async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([
        EVNumber(entry, "porcentaje_actual", "Estado de la Batería", "%", 0, 100, 50.0, "mdi:battery-50"),
        EVNumber(entry, "potencia_carga", "Potencia de Carga", "kW", 0.1, 22.0, entry.data.get(CONF_POTENCIA_CARGA, 1.4), "mdi:ev-plug-type2"),
        EVNumber(entry, "umbral_potencia_solar", "Umbral Producción Solar", "W", 0, 10000, entry.data.get(CONF_UMBRAL_SOLAR, 3000.0), "mdi:white-balance-sunny")
    ])

class EVNumber(NumberEntity):
    def __init__(self, entry, id_name, display_name, uom, min_v, max_v, default, icon):
        self.entity_id = f"number.{DOMAIN}_{id_name}"
        self._attr_name = display_name
        self._attr_unique_id = f"{entry.entry_id}_{id_name}"
        self._attr_native_unit_of_measurement = uom
        self._attr_native_min_value = min_v
        self._attr_native_max_value = max_v
        self._attr_native_value = default
        self._attr_icon = icon

    @property
    def native_value(self):
        """Propiedad estricta para que Home Assistant actualice la tarjeta."""
        return self._attr_native_value

    async def async_set_native_value(self, value: float) -> None:
        """Guarda el valor de forma nativa al soltar el deslizador."""
        self._attr_native_value = float(value)
        self.async_write_ha_state()
