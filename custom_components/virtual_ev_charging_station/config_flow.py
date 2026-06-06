import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import selector
from .const import *

class VirtualEVChargingStationConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="Virtual EV Charging Station", data=user_input)

        # 1. Buscamos dinámicamente los servicios de notificación instalados en tu HA
        notify_services = []
        services = self.hass.services.async_services()
        if "notify" in services:
            notify_services = [f"notify.{svc}" for svc in services["notify"]]
        
        # Añadimos una opción en blanco al principio por si el usuario no quiere notificaciones
        if "" not in notify_services:
            notify_services.insert(0, "")

        # 2. Construimos el formulario
        data_schema = vol.Schema({
            vol.Required(CONF_ENCHUFE): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="switch")
            ),
            vol.Required(CONF_ENERGIA): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor", device_class="energy")
            ),
            vol.Required(CONF_POTENCIA): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor", device_class="power")
            ),
            vol.Required(CONF_SOLAR): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor", device_class="power")
            ),
            vol.Required(CONF_CAPACIDAD, default=13.0): vol.Coerce(float),
            vol.Required(CONF_POTENCIA_CARGA, default=1.4): vol.Coerce(float),
            vol.Required(CONF_UMBRAL_SOLAR, default=3000.0): vol.Coerce(float),
            
            # 3. El campo de notificación ahora es un menú desplegable inteligente
            vol.Optional(CONF_NOTIFICACION, default=""): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=notify_services,
                    custom_value=True, # Permite escribir a mano si el servicio no sale en la lista
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
        })

        return self.async_show_form(step_id="user", data_schema=data_schema)
