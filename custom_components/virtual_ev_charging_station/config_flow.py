import voluptuous as vol
import logging
from homeassistant import config_entries
from homeassistant.helpers import selector
from .const import *

_LOGGER = logging.getLogger(__name__)

class VirtualEVChargingStationConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Paso de configuración del usuario."""
        errors = {}
        
        if user_input is not None:
            # Validación de datos configurados
            try:
                # Verificar que las entidades existen y son accesibles
                enchufe = user_input.get(CONF_ENCHUFE)
                energia = user_input.get(CONF_ENERGIA)
                potencia = user_input.get(CONF_POTENCIA)
                solar = user_input.get(CONF_SOLAR)
                
                _LOGGER.debug(f"[{DOMAIN}] Validando configuración: enchufe={enchufe}, energia={energia}, potencia={potencia}, solar={solar}")
                
                # Validaciones básicas
                if not enchufe or not energia or not potencia or not solar:
                    errors["base"] = "missing_entities"
                    _LOGGER.error(f"[{DOMAIN}] Entidades requeridas faltantes")
                
                # Validación de valores numéricos
                try:
                    cap = float(str(user_input.get(CONF_CAPACIDAD, 13.0)).replace(',', '.'))
                    pot = float(str(user_input.get(CONF_POTENCIA_CARGA, 1.4)).replace(',', '.'))
                    umbral = float(str(user_input.get(CONF_UMBRAL_SOLAR, 3000.0)).replace(',', '.'))
                    
                    if cap <= 0:
                        errors["capacidad_bateria"] = "value_error"
                        _LOGGER.error(f"[{DOMAIN}] Capacidad inválida: {cap}")
                    
                    if pot <= 0:
                        errors["potencia_carga"] = "value_error"
                        _LOGGER.error(f"[{DOMAIN}] Potencia de carga inválida: {pot}")
                    
                    if umbral < 0:
                        errors["umbral_solar"] = "value_error"
                        _LOGGER.error(f"[{DOMAIN}] Umbral solar inválido: {umbral}")
                    
                except ValueError as e:
                    errors["base"] = "invalid_number"
                    _LOGGER.error(f"[{DOMAIN}] Error al parsear números: {e}")
                
                if errors:
                    _LOGGER.warning(f"[{DOMAIN}] Errores en validación: {errors}")
                else:
                    _LOGGER.info(f"[{DOMAIN}] Configuración válida. Creando entrada...")
                    return self.async_create_entry(title="Virtual EV Charging Station", data=user_input)
            
            except Exception as e:
                _LOGGER.error(f"[{DOMAIN}] Error inesperado en validación: {e}", exc_info=True)
                errors["base"] = "unknown"

        # 1. Buscamos dinámicamente los servicios de notificación instalados en tu HA
        notify_services = []
        try:
            services = self.hass.services.async_services()
            if "notify" in services:
                notify_services = sorted([f"notify.{svc}" for svc in services["notify"]])
                _LOGGER.debug(f"[{DOMAIN}] Servicios de notificación encontrados: {notify_services}")
        except Exception as e:
            _LOGGER.warning(f"[{DOMAIN}] Error obteniendo servicios de notificación: {e}")
        
        # Añadimos una opción en blanco al principio por si el usuario no quiere notificaciones
        if "" not in notify_services:
            notify_services.insert(0, "")

        # 2. Construimos el formulario con validaciones
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
            vol.Required(CONF_CAPACIDAD, default=13.0): vol.All(
                vol.Coerce(float),
                vol.Range(min=0.1, max=200)
            ),
            vol.Required(CONF_POTENCIA_CARGA, default=1.4): vol.All(
                vol.Coerce(float),
                vol.Range(min=0.1, max=22.0)
            ),
            vol.Required(CONF_UMBRAL_SOLAR, default=3000.0): vol.All(
                vol.Coerce(float),
                vol.Range(min=0, max=100000)
            ),
            
            # 3. El campo de notificación ahora es un menú desplegable inteligente
            vol.Optional(CONF_NOTIFICACION, default=""): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=notify_services,
                    custom_value=True,  # Permite escribir a mano si el servicio no sale en la lista
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
        })

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
            description_placeholders={
                "docs": "https://github.com/harzt/virtual_ev_charging_station"
            }
        )
