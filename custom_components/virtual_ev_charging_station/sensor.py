import logging
from datetime import timedelta
from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.core import callback
from .const import DOMAIN, CONF_CAPACIDAD

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities):
    """Configura los sensores."""
    try:
        _LOGGER.info(f"[{DOMAIN}] Configurando sensores...")
        async_add_entities([
            EVSensor(entry, "energia_restante_80", "Restante al 80%", "kWh", "mdi:battery-charging-80"),
            EVSensor(entry, "tiempo_restante", "Tiempo Restante", None, "mdi:timer-sand")
        ])
        _LOGGER.debug(f"[{DOMAIN}] Sensores configurados correctamente")
    except Exception as e:
        _LOGGER.error(f"[{DOMAIN}] Error configurando sensores: {e}", exc_info=True)

class EVSensor(SensorEntity):
    """Entidad sensor para energía y tiempo restante."""
    
    def __init__(self, entry, id_name, display_name, uom, icon):
        self.entity_id = f"sensor.{DOMAIN}_{id_name}"
        self._attr_name = display_name
        self._attr_unique_id = f"{entry.entry_id}_{id_name}"
        self._attr_native_unit_of_measurement = uom
        self._attr_icon = icon
        self._id_name = id_name
        self._entry = entry
        
        # Parsear capacidad con manejo de errores
        try:
            capacidad_raw = str(entry.data.get(CONF_CAPACIDAD, 13.0)).replace(',', '.')
            self._capacidad = float(capacidad_raw)
            _LOGGER.debug(f"[{DOMAIN}] Capacidad parseada: {self._capacidad} kWh")
        except (ValueError, TypeError) as e:
            _LOGGER.warning(f"[{DOMAIN}] Error parseando capacidad: {e}, usando default 13.0 kWh")
            self._capacidad = 13.0
        
        self._attr_native_value = None

    async def async_added_to_hass(self):
        """Se ejecuta cuando el sensor se añade a Home Assistant."""
        try:
            _LOGGER.debug(f"[{DOMAIN}] Sensor {self._id_name} añadido a Home Assistant")
            
            # Escucha al instante el evento de que has movido un slider
            self.async_on_remove(self.hass.bus.async_listen("virtual_ev_recalc", self._update_math))
            
            # Y además recálcula cada 3 segundos como red de seguridad
            self.async_on_remove(async_track_time_interval(self.hass, self._update_math, timedelta(seconds=3)))
            
            # Actualización inicial
            self._update_math(None)
            _LOGGER.debug(f"[{DOMAIN}] Sensor {self._id_name} inicializado")
        except Exception as e:
            _LOGGER.error(f"[{DOMAIN}] Error en async_added_to_hass para {self._id_name}: {e}", exc_info=True)

    @callback
    def _update_math(self, event=None):
        """Actualiza los cálculos del sensor."""
        try:
            pct_bateria = 50.0
            pot_carga = 1.4

            # Obtener porcentaje actual
            st_pct = self.hass.states.get(f"number.{DOMAIN}_porcentaje_actual")
            if st_pct and st_pct.state not in ["unknown", "unavailable"]:
                try:
                    pct_bateria = float(st_pct.state)
                    _LOGGER.debug(f"[{DOMAIN}] Porcentaje batería: {pct_bateria}%")
                except ValueError as e:
                    _LOGGER.warning(f"[{DOMAIN}] Error parseando porcentaje: {e}")
            else:
                _LOGGER.debug(f"[{DOMAIN}] Estado de porcentaje no disponible")

            # Obtener potencia de carga
            st_pot = self.hass.states.get(f"number.{DOMAIN}_potencia_carga")
            if st_pot and st_pot.state not in ["unknown", "unavailable"]:
                try:
                    pot_carga = float(st_pot.state)
                    _LOGGER.debug(f"[{DOMAIN}] Potencia de carga: {pot_carga} kW")
                except ValueError as e:
                    _LOGGER.warning(f"[{DOMAIN}] Error parseando potencia: {e}")
            else:
                _LOGGER.debug(f"[{DOMAIN}] Estado de potencia no disponible")

            # Calcular energía faltante para llegar al 80%
            energia_faltante = max(0.0, (80.0 - pct_bateria) * self._capacidad / 100.0)
            
            if self._id_name == "energia_restante_80":
                self._attr_native_value = round(energia_faltante, 2)
                _LOGGER.debug(f"[{DOMAIN}] Energía restante al 80%: {self._attr_native_value} kWh")
            
            elif self._id_name == "tiempo_restante":
                if pot_carga <= 0:
                    pot_carga = 1.4
                    _LOGGER.warning(f"[{DOMAIN}] Potencia inválida, usando default 1.4 kW")
                
                horas = energia_faltante / pot_carga
                h = int(horas)
                m = int((horas - h) * 60)
                self._attr_native_value = f"{h}h {m}m"
                _LOGGER.debug(f"[{DOMAIN}] Tiempo restante: {self._attr_native_value}")
            
            self.async_write_ha_state()
        
        except Exception as e:
            _LOGGER.error(f"[{DOMAIN}] Error en _update_math para {self._id_name}: {e}", exc_info=True)
