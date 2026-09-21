import voluptuous as vol
import logging
from homeassistant import config_entries
from homeassistant.helpers import selector
from .const import (
    DOMAIN, CONF_ENCHUFE, CONF_ENERGIA, CONF_POTENCIA, CONF_SOLAR,
    CONF_CAPACIDAD, CONF_POTENCIA_CARGA, CONF_UMBRAL_SOLAR, CONF_NOTIFICACION
)

_LOGGER = logging.getLogger(__name__)

class VirtualEVChargingStationConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def _validar_entrada(self, user_input):
        """Valida los datos introducidos por el usuario. Devuelve el dict de errores."""
        errors = {}
        try:
            enchufe = user_input.get(CONF_ENCHUFE)
            energia = user_input.get(CONF_ENERGIA)
            potencia = user_input.get(CONF_POTENCIA)
            solar = user_input.get(CONF_SOLAR)

            _LOGGER.debug(f"[{DOMAIN}] Validando configuración: enchufe={enchufe}, energia={energia}, potencia={potencia}, solar={solar}")

            if not enchufe or not energia or not potencia or not solar:
                errors["base"] = "missing_entities"
                _LOGGER.error(f"[{DOMAIN}] Entidades requeridas faltantes")

            try:
                cap = float(str(user_input.get(CONF_CAPACIDAD, 13.0)).replace(',', '.'))
                pot = float(str(user_input.get(CONF_POTENCIA_CARGA, 1.5)).replace(',', '.'))
                umbral = float(str(user_input.get(CONF_UMBRAL_SOLAR, 3000.0)).replace(',', '.'))

                if cap <= 0:
                    errors[CONF_CAPACIDAD] = "value_error"
                if pot <= 0:
                    errors[CONF_POTENCIA_CARGA] = "value_error"
                if umbral < 0:
                    errors[CONF_UMBRAL_SOLAR] = "value_error"

            except ValueError as e:
                errors["base"] = "invalid_number"
                _LOGGER.error(f"[{DOMAIN}] Error al parsear números: {e}")

        except Exception as e:
            _LOGGER.error(f"[{DOMAIN}] Error inesperado en validación: {e}", exc_info=True)
            errors["base"] = "unknown"

        return errors

    def _notify_services(self):
        notify_services = []
        try:
            services = self.hass.services.async_services()
            if "notify" in services:
                notify_services = sorted([f"notify.{svc}" for svc in services["notify"]])
        except Exception:
            pass

        if "" not in notify_services:
            notify_services.insert(0, "")

        return notify_services

    def _build_schema(self, notify_services, defaults):
        """Construye el formulario, precargando valores previos si se pasan (reconfigurar)."""

        def _req_entidad(key):
            val = defaults.get(key)
            return vol.Required(key, default=val) if val else vol.Required(key)

        def _req_num(key, fallback):
            return vol.Required(key, default=float(defaults.get(key, fallback)))

        # FORMULARIO LIBERADO DE RESTRICCIONES DE DEVICE_CLASS
        return vol.Schema({
            _req_entidad(CONF_ENCHUFE): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="switch")
            ),
            # Quitamos los device_class restrictivos para que Victron/Fronius salgan siempre
            _req_entidad(CONF_ENERGIA): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor")
            ),
            _req_entidad(CONF_POTENCIA): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor")
            ),
            _req_entidad(CONF_SOLAR): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor")
            ),
            _req_num(CONF_CAPACIDAD, 14.4): vol.All(
                vol.Coerce(float),
                vol.Range(min=0.1, max=200)
            ),
            _req_num(CONF_POTENCIA_CARGA, 1.4): vol.All(
                vol.Coerce(float),
                vol.Range(min=0.1, max=22.0)
            ),
            _req_num(CONF_UMBRAL_SOLAR, 3000.0): vol.All(
                vol.Coerce(float),
                vol.Range(min=0, max=100000)
            ),
            vol.Optional(CONF_NOTIFICACION, default=defaults.get(CONF_NOTIFICACION, "")): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=notify_services,
                    custom_value=True,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
        })

    async def async_step_user(self, user_input=None):
        """Paso de configuración inicial del usuario."""
        errors = {}

        if user_input is not None:
            errors = self._validar_entrada(user_input)

            if not errors:
                enchufe = user_input.get(CONF_ENCHUFE)
                await self.async_set_unique_id(enchufe)
                self._abort_if_unique_id_configured()
                _LOGGER.info(f"[{DOMAIN}] Configuración válida. Creando entrada...")
                return self.async_create_entry(title="Virtual EV Station", data=user_input)

        schema = self._build_schema(self._notify_services(), user_input or {})
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_reconfigure(self, user_input=None):
        """Permite cambiar las entidades/parámetros de una estación ya configurada."""
        entry_id = self.context["entry_id"]
        reconfigure_entry = self.hass.config_entries.async_get_entry(entry_id)
        errors = {}

        if user_input is not None:
            errors = self._validar_entrada(user_input)

            if not errors:
                enchufe = user_input.get(CONF_ENCHUFE)
                for otra_entrada in self.hass.config_entries.async_entries(DOMAIN):
                    if otra_entrada.entry_id != entry_id and otra_entrada.data.get(CONF_ENCHUFE) == enchufe:
                        errors["base"] = "already_configured"
                        _LOGGER.error(f"[{DOMAIN}] El enchufe {enchufe} ya está en uso por otra estación")

            if not errors:
                _LOGGER.info(f"[{DOMAIN}] Reconfiguración válida. Recargando entrada {entry_id}...")
                self.hass.config_entries.async_update_entry(
                    reconfigure_entry, data=user_input, unique_id=enchufe
                )
                await self.hass.config_entries.async_reload(entry_id)
                return self.async_abort(reason="reconfigure_successful")

        schema = self._build_schema(self._notify_services(), user_input or reconfigure_entry.data)
        return self.async_show_form(step_id="reconfigure", data_schema=schema, errors=errors)
