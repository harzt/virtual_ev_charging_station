import logging
import re
from datetime import timedelta
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_interval
from .const import DOMAIN, PLATFORMS, CONF_ENCHUFE, CONF_ENERGIA, CONF_POTENCIA, CONF_SOLAR, CONF_NOTIFICACION

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "energia_meta": 0.0,
        "bms_ticks": 0,
        "notificado_80": False,
        "ultimo_pct": -1.0
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    conf_enchufe = entry.data.get("enchufe_switch") or entry.data.get(CONF_ENCHUFE)
    conf_energia = entry.data.get("enchufe_energia") or entry.data.get(CONF_ENERGIA)
    conf_potencia = entry.data.get("enchufe_potencia") or entry.data.get(CONF_POTENCIA)
    conf_solar = entry.data.get("sensor_solar") or entry.data.get(CONF_SOLAR)

    def get_float(eid, default=0.0):
        if not eid: return default
        st = hass.states.get(eid)
        if not st or st.state in ["unknown", "unavailable"]: return default
        try:
            s = str(st.state).replace(',', '.')
            s = re.sub(r'[^\d\.\-]', '', s)
            if not s: return default
            val = float(s)
            uom = st.attributes.get("unit_of_measurement", "").lower()
            if "kw" in uom and "kwh" not in uom: val *= 1000.0
            if uom == "wh": val /= 1000.0
            return val
        except: return default

    async def enviar_msg(titulo, mensaje):
        srv = entry.data.get("servicio_notificacion") or entry.data.get(CONF_NOTIFICACION, "")
        if not srv: return
        try:
            parts = srv.strip().split(".")
            if len(parts) == 2:
                await hass.services.async_call(parts[0], parts[1], {"title": titulo, "message": mensaje})
            else:
                await hass.services.async_call("notify", srv.strip(), {"title": titulo, "message": mensaje})
        except: pass

    async def nucleo_maestro(_):
        if not conf_enchufe: return

        id_solar = f"switch.{DOMAIN}_modo_automatico_solar"
        id_red = f"switch.{DOMAIN}_forzar_carga_red"
        id_umbral = f"number.{DOMAIN}_umbral_potencia_solar"
        id_pct = f"number.{DOMAIN}_porcentaje_actual"
        id_restante = f"sensor.{DOMAIN}_energia_restante_80"

        modo_solar = hass.states.is_on(id_solar)
        modo_red = hass.states.is_on(id_red)
        enchufe_on = hass.states.is_on(conf_enchufe)

        umbral = get_float(id_umbral, 3000.0)
        pot_sol = get_float(conf_solar)
        pct_actual = get_float(id_pct, -1.0)
        data = hass.data[DOMAIN][entry.entry_id]

        if pct_actual != -1.0 and data["ultimo_pct"] != pct_actual:
            data["ultimo_pct"] = pct_actual
            data["energia_meta"] = 0.0
            data["notificado_80"] = False

        debe_encender = False
        if modo_red: debe_encender = True
        elif modo_solar and pot_sol >= umbral: debe_encender = True

        if debe_encender and not enchufe_on:
            await hass.services.async_call("homeassistant", "turn_on", {"entity_id": conf_enchufe})
            if data["energia_meta"] == 0.0:
                data["energia_meta"] = get_float(conf_energia) + get_float(id_restante)
                data["notificado_80"] = False
                await enviar_msg("⚡ Moto Cargando", "Carga por Red (100%)." if modo_red else "Carga Solar (80%).")

        elif not debe_encender and enchufe_on:
            # NUEVO: ¡Modo Override! Solo apagamos si estábamos gestionando nosotros la carga (meta > 0).
            # Si meta es 0, significa que encendiste el proxy manualmente y te dejamos en paz.
            if data["energia_meta"] > 0 or data["bms_ticks"] > 0:
                await hass.services.async_call("homeassistant", "turn_off", {"entity_id": conf_enchufe})
                data["energia_meta"] = 0.0
                data["bms_ticks"] = 0

        # SEGURIDAD Y CORTES
        if debe_encender and enchufe_on:
            meta = data["energia_meta"]
            actual = get_float(conf_energia)

            if meta > 0 and actual >= meta:
                if not modo_red:
                    await hass.services.async_call("homeassistant", "turn_off", {"entity_id": conf_enchufe})
                    await hass.services.async_call("homeassistant", "turn_off", {"entity_id": id_solar})
                    data["energia_meta"] = 0.0
                    await enviar_msg("🔋 80% Alcanzado", "Carga Solar Finalizada.")
                elif not data["notificado_80"]:
                    data["notificado_80"] = True
                    await enviar_msg("⏳ 80% Superado", "El modo Red sigue inyectando hacia el 100%.")

            pot_bms = get_float(conf_potencia)
            if 0.1 < pot_bms < 15.0:
                data["bms_ticks"] += 1
                if data["bms_ticks"] >= 5:
                    await hass.services.async_call("homeassistant", "turn_off", {"entity_id": conf_enchufe})
                    await hass.services.async_call("homeassistant", "turn_off", {"entity_id": id_red})
                    await hass.services.async_call("homeassistant", "turn_off", {"entity_id": id_solar})
                    data["energia_meta"] = 0.0
                    data["bms_ticks"] = 0
                    await enviar_msg("🔋 100% Alcanzado", "Batería llena. Corriente cortada.")
            else:
                data["bms_ticks"] = 0

    entry.async_on_unload(async_track_time_interval(hass, nucleo_maestro, timedelta(seconds=2)))
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok: hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
