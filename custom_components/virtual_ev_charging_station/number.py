import logging
from homeassistant.components.number import NumberEntity
from .const import DOMAIN, CONF_POTENCIA_CARGA, CONF_UMBRAL_SOLAR

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities):
    """Configura las entidades numéricas."""
    try:
        _LOGGER.info(f"[{DOMAIN}] Configurando números...")
        
        # Obtener valores configurados o defaults
        potencia_carga = entry.data.get(CONF_POTENCIA_CARGA, 1.5)
        umbral_solar = entry.data.get(CONF_UMBRAL_SOLAR, 3500)
        
        try:
            potencia_carga = float(str(potencia_carga).replace(',', '.'))
        except (ValueError, TypeError):
            _LOGGER.warning(f"[{DOMAIN}] Potencia de carga inválida: {potencia_carga}, usando default 1.5")
            potencia_carga = 1.5
        
        try:
            umbral_solar = float(str(umbral_solar).replace(',', '.'))
        except (ValueError, TypeError):
            _LOGGER.warning(f"[{DOMAIN}] Umbral solar inválido: {umbral_solar}, usando default 3500")
            umbral_solar = 3500
        
        async_add_entities([
            EVNumber(entry, "porcentaje_actual", "Estado de la Batería", "%", 0, 100, 50.0, "mdi:battery-50"),
            EVNumber(entry, "potencia_carga", "Potencia de Carga", "kW", 0.1, 11.0, potencia_carga, "mdi:ev-plug-type2"),
            EVNumber(entry, "umbral_potencia_solar", "Umbral Producción Solar", "W", 0, 10000, umbral_solar, "mdi:white-balance-sunny")
        ])
        _LOGGER.debug(f"[{DOMAIN}] Números configurados correctamente")
    except Exception as e:
        _LOGGER.error(f"[{DOMAIN}] Error configurando números: {e}", exc_info=True)

class EVNumber(NumberEntity):
    """Entidad número para controles deslizables."""
    
    def __init__(self, entry, id_name, display_name, uom, min_v, max_v, default, icon):
        self.entity_id = f"number.{DOMAIN}_{id_name}"
        self._attr_name = display_name
        self._attr_unique_id = f"{entry.entry_id}_{id_name}"
        self._attr_native_unit_of_measurement = uom
        self._attr_native_min_value = min_v
        self._attr_native_max_value = max_v
        self._attr_native_value = default
        self._attr_icon = icon
        self._id_name = id_name
        self._entry = entry
        
        _LOGGER.debug(f"[{DOMAIN}] Número {id_name} inicializado: {default} {uom} (rango {min_v}-{max_v})")

    @property
    def native_value(self):
        """Retorna el valor actual."""
        return self._attr_native_value

    async def async_set_native_value(self, value: float) -> None:
        """Establece un nuevo valor."""
        try:
            value = float(value)
            
            # Validar que el valor esté en rango
            if value < self._attr_native_min_value or value > self._attr_native_max_value:
                _LOGGER.warning(
                    f"[{DOMAIN}] Valor fuera de rango para {self._id_name}: {value} "
                    f"(rango permitido: {self._attr_native_min_value}-{self._attr_native_max_value})"
                )
                value = max(self._attr_native_min_value, min(value, self._attr_native_max_value))
            
            self._attr_native_value = float(value)
            self.async_write_ha_state()
            
            # Disparar evento de recálculo
            self.hass.bus.async_fire("virtual_ev_recalc")
            
            _LOGGER.info(f"[{DOMAIN}] Número {self._id_name} actualizado a {self._attr_native_value} {self._attr_native_unit_of_measurement}")
        
        except (ValueError, TypeError) as e:
            _LOGGER.error(f"[{DOMAIN}] Error estableciendo valor en {self._id_name}: {e}", exc_info=True)
