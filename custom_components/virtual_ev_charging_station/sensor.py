from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.core import callback
from .const import DOMAIN, CONF_CAPACIDAD

async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([
        EVSensor(entry, "energia_restante_80", "Restante al 80%", "kWh", "mdi:battery-charging-80"),
        EVSensor(entry, "tiempo_restante", "Tiempo Restante", None, "mdi:timer-sand")
    ])

class EVSensor(SensorEntity):
    def __init__(self, entry, id_name, display_name, uom, icon):
        self._entry = entry
        self.entity_id = f"sensor.{DOMAIN}_{id_name}"
        self._attr_name = display_name
        self._attr_unique_id = f"{entry.entry_id}_{id_name}"
        self._attr_native_unit_of_measurement = uom
        self._attr_icon = icon
        self._id_name = id_name
        try: self._capacidad = float(str(entry.data.get(CONF_CAPACIDAD, 13.0)).replace(',', '.'))
        except: self._capacidad = 13.0

    async def async_added_to_hass(self):
        """Rastreador nativo: elimina cualquier desfase de la base de datos."""
        id_pct = f"number.{DOMAIN}_porcentaje_actual"
        id_pot = f"number.{DOMAIN}_potencia_carga"
        
        async def _recalcular_sensor(event):
            self._update_math()

        self.async_on_remove(async_track_state_change_event(self.hass, [id_pct, id_pot], _recalcular_sensor))
        self._update_math()

    @callback
    def _update_math(self):
        pct_bateria = 50.0
        pot_carga = 1.4

        st_pct = self.hass.states.get(f"number.{DOMAIN}_porcentaje_actual")
        if st_pct and st_pct.state not in ["unknown", "unavailable"]:
            try: pct_bateria = float(st_pct.state)
            except: pass

        st_pot = self.hass.states.get(f"number.{DOMAIN}_potencia_carga")
        if st_pot and st_pot.state not in ["unknown", "unavailable"]:
            try: pot_carga = float(st_pot.state)
            except: pass

        energia_faltante = max(0.0, (80.0 - pct_bateria) * self._capacidad / 100.0)
        
        if self._id_name == "energia_restante_80":
            self._attr_native_value = round(energia_faltante, 2)
        elif self._id_name == "tiempo_restante":
            if pot_carga <= 0: pot_carga = 1.4
            horas = energia_faltante / pot_carga
            h = int(horas)
            m = int((horas - h) * 60)
            self._attr_native_value = f"{h}h {m}m"
            
        self.async_write_ha_state()