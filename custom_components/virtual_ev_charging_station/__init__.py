import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_state_change_event, async_call_later
from .const import DOMAIN, PLATFORMS, CONF_ENCHUFE, CONF_ENERGIA, CONF_POTENCIA, CONF_SOLAR, CONF_NOTIFICACION

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})
    data = {
        "meta_kwh": 0.0,
        "bms_cancel": None,
        "notificado_80": False,
        "enchufe_estaba_on": False
    }
    hass.data[DOMAIN][entry.entry_id] = data

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Forzamos switch.moto por código como red de seguridad incondicional
    enchufe = entry.data.get("enchufe_switch") or entry.data.get(CONF_ENCHUFE) or "switch.moto"
    energia = entry.data.get("enchufe_energia") or entry.data.get(CONF_ENERGIA)
    potencia = entry.data.get("enchufe_potencia") or entry.data.get(CONF_POTENCIA)
    solar = entry.data.get("sensor_solar") or entry.data.get(CONF_SOLAR)

    sw_solar = f"switch.{DOMAIN}_modo_automatico_solar"
    sw_red = f"switch.{DOMAIN}_forzar_carga_red"
    num_umbral = f"number.{DOMAIN}_umbral_potencia_solar"
    sens_restante = f"sensor.{DOMAIN}_energia_restante_80"

    def get_val(eid):
        try:
            st = hass.states.get(eid)
            if st and st.state not in ["unknown", "unavailable"]:
                val = float(str(st.state).replace(',', '.'))
                uom = st.attributes.get("unit_of_measurement", "").lower()
                if "kw" in uom and "kwh" not in uom: val *= 1000.0
                if uom == "wh": val /= 1000.0
                return val
        except: pass
        return 0.0

    async def enviar_msg(titulo, mensaje):
        srv = entry.data.get("servicio_notificacion") or entry.data.get(CONF_NOTIFICACION, "")
        if not srv: return
        try:
            parts = srv.strip().split(".")
            await hass.services.async_call(parts[0], parts[1], {"title": titulo, "message": mensaje})
        except: pass

    async def trigger_automatizacion(event=None):
        if not enchufe: return

        is_on = hass.states.is_on(enchufe)
        is_solar = hass.states.is_on(sw_solar)
        is_red = hass.states.is_on(sw_red)

        val_solar = get_val(solar)
        val_umbral = get_val(num_umbral)
        val_energia = get_val(energia)
        val_potencia = get_val(potencia)

        # Captura de inicio físico de carga
        if is_on and not data["enchufe_estaba_on"]:
            data["meta_kwh"] = val_energia + get_val(sens_restante)
            data["notificado_80"] = False
            if is_red or is_solar:
                msg = "Carga por Red (100%)." if is_red else "Carga Solar (80%)."
                await enviar_msg("⚡ Moto Cargando", msg)
        
        elif not is_on and data["enchufe_estaba_on"]:
            data["meta_kwh"] = 0.0
            if data["bms_cancel"]:
                data["bms_cancel"]()
                data["bms_cancel"] = None

        data["enchufe_estaba_on"] = is_on

        # REGLA DE ENCENDIDO IMPLACABLE
        if not is_on:
            # Si se activa Forzar Carga Red, enciende ignorando todo lo demás
            # Si se cumple el umbral solar, enciende automáticamente
            if is_red or (is_solar and val_solar >= val_umbral):
                await hass.services.async_call("homeassistant", "turn_on", {"entity_id": enchufe})
                return

        # REGLAS DE APAGADO
        if is_on:
            # Si estamos en modo Red, ignoramos el sol y el límite del 80%
            if is_red:
                if 0 < val_potencia < 15:
                    if not data["bms_cancel"]:
                        async def _corte_red_bms(_):
                            data["bms_cancel"] = None
                            await hass.services.async_call("homeassistant", "turn_off", {"entity_id": enchufe})
                            await hass.services.async_call("homeassistant", "turn_off", {"entity_id": sw_red})
                            await hass.services.async_call("homeassistant", "turn_off", {"entity_id": sw_solar})
                            await enviar_msg("🔋 100% Alcanzado", "Batería llena (Modo Red). Corriente cortada.")
                        data["bms_cancel"] = async_call_later(hass, 10, _corte_red_bms)
                else:
                    if data["bms_cancel"]: data["bms_cancel"](); data["bms_cancel"] = None
                return

            # Si NO es modo Red, evaluamos las reglas del Modo Solar
            if is_solar:
                # Apagado automático por caída de sol
                if val_solar < val_umbral:
                    await hass.services.async_call("homeassistant", "turn_off", {"entity_id": enchufe})
                    return

                # Apagado automático al llegar al 80%
                if data["meta_kwh"] > 0 and val_energia >= data["meta_kwh"]:
                    await hass.services.async_call("homeassistant", "turn_off", {"entity_id": enchufe})
                    await hass.services.async_call("homeassistant", "turn_off", {"entity_id": sw_solar})
                    await enviar_msg("🔋 80% Alcanzado", "Carga Solar Finalizada.")
                    return

                # Parada por batería llena (100%)
                if 0 < val_potencia < 15:
                    if not data["bms_cancel"]:
                        async def _corte_solar_bms(_):
                            data["bms_cancel"] = None
                            await hass.services.async_call("homeassistant", "turn_off", {"entity_id": enchufe})
                            await hass.services.async_call("homeassistant", "turn_off", {"entity_id": sw_solar})
                            await enviar_msg("🔋 100% Alcanzado", "Batería llena (Modo Solar). Corriente cortada.")
                        data["bms_cancel"] = async_call_later(hass, 10, _corte_solar_bms)
                else:
                    if data["bms_cancel"]: data["bms_cancel"](); data["bms_cancel"] = None

    # Agrupación nativa de todas las entidades involucradas
    entidades_maestras = [enchufe, solar, energia, potencia, sw_solar, sw_red, num_umbral, sens_restante]
    entidades_maestras = [e for e in entidades_maestras if e]

    # Escucha de cambios de estado nativa
    entry.async_on_unload(async_track_state_change_event(hass, entidades_maestras, trigger_automatizacion))
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok: hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok