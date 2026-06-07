import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_state_change_event
from .const import (
    DOMAIN, PLATFORMS, CONF_ENCHUFE, CONF_ENERGIA, 
    CONF_POTENCIA, CONF_SOLAR, CONF_NOTIFICACION
)

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})
    data = {
        "energia_corte": 0.0,
        "enchufe_estaba_on": False,
        "notificado_80": False,
        "bms_ticks": 0
    }
    hass.data[DOMAIN][entry.entry_id] = data

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # 1. EXTRACCIÓN ESTRICTA DE LAS ENTIDADES CONFIGURADAS
    conf_enchufe = entry.data.get(CONF_ENCHUFE)
    conf_energia = entry.data.get(CONF_ENERGIA)
    conf_potencia = entry.data.get(CONF_POTENCIA)
    conf_solar = entry.data.get(CONF_SOLAR)

    # Comprobación de seguridad
    if not conf_enchufe:
        _LOGGER.error(f"EV Station: Error crítico. No se detecta '{CONF_ENCHUFE}' en la configuración.")
        return False

    # Entidades generadas por la integración
    sw_solar = f"switch.{DOMAIN}_modo_automatico_solar"
    sw_red = f"switch.{DOMAIN}_forzar_carga_red"
    num_umbral = f"number.{DOMAIN}_umbral_potencia_solar"
    sens_restante = f"sensor.{DOMAIN}_energia_restante_80"

    def get_float(eid, default=0.0):
        st = hass.states.get(eid)
        if not st or st.state in ["unknown", "unavailable"]: return default
        try:
            s = str(st.state).replace(',', '.')
            val = float(''.join(c for c in s if c.isdigit() or c in '.-'))
            uom = st.attributes.get("unit_of_measurement", "").lower()
            if "kw" in uom and "kwh" not in uom: val *= 1000.0
            if uom == "wh": val /= 1000.0
            return val
        except: return default

    async def enviar_msg(titulo, mensaje):
        srv = entry.data.get(CONF_NOTIFICACION, "")
        if not srv: return
        try:
            parts = srv.strip().split(".")
            await hass.services.async_call(parts[0], parts[1], {"title": titulo, "message": mensaje})
        except: pass

    async def evaluar_logica(event=None):
        is_on = hass.states.is_on(conf_enchufe)
        is_red = hass.states.is_on(sw_red)
        is_solar = hass.states.is_on(sw_solar)

        val_solar = get_float(conf_solar)
        val_umbral = get_float(num_umbral, 3000.0)
        val_energia = get_float(conf_energia)
        val_potencia = get_float(conf_potencia)
        val_restante = get_float(sens_restante)

        # INICIO DE CARGA
        if is_on and not data["enchufe_estaba_on"]:
            data["energia_corte"] = val_energia + val_restante
            data["notificado_80"] = False
            data["bms_ticks"] = 0
            if is_red or is_solar:
                msg = "Carga por Red (100%)." if is_red else "Carga Solar (80%)."
                await enviar_msg("⚡ Moto Cargando", msg)

        # FIN DE CARGA
        elif not is_on and data["enchufe_estaba_on"]:
            data["energia_corte"] = 0.0
            data["bms_ticks"] = 0

        data["enchufe_estaba_on"] = is_on

        # REGLAS DE ENCENDIDO IMPLACABLES (Apunta a tu enchufe configurado)
        if not is_on:
            if is_red or (is_solar and val_solar >= val_umbral):
                await hass.services.async_call("switch", "turn_on", {"entity_id": conf_enchufe})
                return

        # REGLAS DE APAGADO
        if is_on:
            if is_red:
                if 0 < val_potencia < 15:
                    data["bms_ticks"] += 1
                    if data["bms_ticks"] >= 3:
                        await hass.services.async_call("switch", "turn_off", {"entity_id": conf_enchufe})
                        await hass.services.async_call("switch", "turn_off", {"entity_id": sw_red})
                        await hass.services.async_call("switch", "turn_off", {"entity_id": sw_solar})
                        await enviar_msg("🔋 100% Alcanzado", "Batería llena. Corriente cortada.")
                else:
                    data["bms_ticks"] = 0
                return

            if is_solar:
                if val_solar < val_umbral:
                    await hass.services.async_call("switch", "turn_off", {"entity_id": conf_enchufe})
                    return
                
                if data["energia_corte"] > 0 and val_energia >= data["energia_corte"]:
                    await hass.services.async_call("switch", "turn_off", {"entity_id": conf_enchufe})
                    await hass.services.async_call("switch", "turn_off", {"entity_id": sw_solar})
                    await enviar_msg("🔋 80% Alcanzado", "Carga Solar Finalizada.")
                    return

                if 0 < val_potencia < 15:
                    data["bms_ticks"] += 1
                    if data["bms_ticks"] >= 3:
                        await hass.services.async_call("switch", "turn_off", {"entity_id": conf_enchufe})
                        await hass.services.async_call("switch", "turn_off", {"entity_id": sw_solar})
                        await enviar_msg("🔋 100% Alcanzado", "Batería llena. Corriente cortada.")
                else:
                    data["bms_ticks"] = 0

    # Escucha estrictamente las entidades que metiste en la configuración y las de la tarjeta
    entidades_vigiladas = [
        conf_enchufe, conf_solar, conf_energia, conf_potencia,
        sw_solar, sw_red, num_umbral, sens_restante
    ]
    entidades_vigiladas = [e for e in entidades_vigiladas if e]

    entry.async_on_unload(
        async_track_state_change_event(hass, entidades_vigiladas, evaluar_logica)
    )

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok: hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok