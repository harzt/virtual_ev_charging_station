import logging
from datetime import timedelta
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import STORAGE_DIR
import homeassistant.helpers.entity_registry as er
from .const import (
    DOMAIN, PLATFORMS, CONF_ENCHUFE, CONF_ENERGIA, 
    CONF_POTENCIA, CONF_SOLAR, CONF_NOTIFICACION
)
import json
import os

_LOGGER = logging.getLogger(__name__)

STORAGE_FILE = "virtual_ev_charging_station_state.json"

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    _LOGGER.info(f"[{DOMAIN}] Inicializando integración v1.1.0 Final")
    
    hass.data.setdefault(DOMAIN, {})
    
    data = {
        "energia_corte": 0.0,
        "enchufe_estaba_on": False,
        "notificado_80": False,
        "bms_ticks": 0,
    }
    
    storage_path = hass.config.path(STORAGE_DIR, STORAGE_FILE)
    try:
        if os.path.exists(storage_path):
            with open(storage_path, 'r', encoding='utf-8') as f:
                stored_data = json.load(f)
                if entry.entry_id in stored_data:
                    data.update(stored_data[entry.entry_id])
    except Exception:
        pass
    
    hass.data[DOMAIN][entry.entry_id] = data
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    conf_enchufe = entry.data.get(CONF_ENCHUFE)
    conf_energia = entry.data.get(CONF_ENERGIA)
    conf_potencia = entry.data.get(CONF_POTENCIA)
    conf_solar = entry.data.get(CONF_SOLAR)

    if not conf_enchufe: return False

    ent_reg = er.async_get(hass)
    
    def get_real_id(dtype, name):
        eid = ent_reg.async_get_entity_id(dtype, DOMAIN, f"{entry.entry_id}_{name}")
        return eid if eid else f"{dtype}.{DOMAIN}_{name}"

    sw_solar = get_real_id("switch", "modo_automatico_solar")
    sw_red = get_real_id("switch", "forzar_carga_red")
    num_umbral = get_real_id("number", "umbral_potencia_solar")
    sens_restante = get_real_id("sensor", "energia_restante_80")

    # LA CORRECCIÓN LEGAL DE ESTADOS ESTÁ AQUÍ
    def is_state_on(eid):
        st = hass.states.get(eid)
        return st is not None and st.state == "on"

    def get_float(eid, default=0.0):
        try:
            st = hass.states.get(eid)
            if not st or st.state in ["unknown", "unavailable", ""]: return default
            s = str(st.state).strip().replace('W', '').replace('w', '').replace(' ', '')
            s = s.replace(',', '.')
            parts = s.split('.')
            if len(parts) > 2:
                s = ''.join(parts[:-1]) + '.' + parts[-1]
            val = float(s)
            uom = st.attributes.get("unit_of_measurement", "").lower()
            if "kw" in uom and "kwh" not in uom: val *= 1000.0
            if uom == "wh": val /= 1000.0
            return val
        except Exception:
            return default

    async def guardar_estado():
        try:
            os.makedirs(os.path.dirname(storage_path), exist_ok=True)
            all_data = {}
            if os.path.exists(storage_path):
                with open(storage_path, 'r', encoding='utf-8') as f:
                    all_data = json.load(f)
            all_data[entry.entry_id] = data
            with open(storage_path, 'w', encoding='utf-8') as f:
                json.dump(all_data, f, indent=2)
        except Exception:
            pass

    async def enviar_msg(titulo, mensaje):
        srv = entry.data.get(CONF_NOTIFICACION, "")
        if not srv: return
        try:
            parts = srv.strip().split(".")
            if len(parts) != 2: return
            await hass.services.async_call(parts[0], parts[1], {"title": titulo, "message": mensaje})
        except Exception:
            pass

    async def evaluar_logica(_=None):
        try:
            is_on = is_state_on(conf_enchufe)
            is_red = is_state_on(sw_red)
            is_solar = is_state_on(sw_solar)

            val_solar = get_float(conf_solar)
            val_umbral = get_float(num_umbral, 3000.0)
            val_energia = get_float(conf_energia)
            val_potencia = get_float(conf_potencia)
            val_restante = get_float(sens_restante)

            if is_on and not data["enchufe_estaba_on"]:
                data["energia_corte"] = val_energia + val_restante
                data["notificado_80"] = False
                data["bms_ticks"] = 0
                if is_red or is_solar:
                    msg = "Carga por Red (100%)." if is_red else "Carga Solar (80%)."
                    await enviar_msg("⚡ Moto Cargando", msg)

            elif not is_on and data["enchufe_estaba_on"]:
                data["energia_corte"] = 0.0
                data["bms_ticks"] = 0

            data["enchufe_estaba_on"] = is_on

            # === REGLAS DE ENCENDIDO ===
            if not is_on:
                if is_red:
                    await hass.services.async_call("homeassistant", "turn_on", {"entity_id": conf_enchufe})
                    return
                if is_solar and val_solar >= val_umbral:
                    await hass.services.async_call("homeassistant", "turn_on", {"entity_id": conf_enchufe})
                    return

            # === REGLAS DE APAGADO ===
            if is_on:
                if not is_red and not is_solar:
                    await hass.services.async_call("homeassistant", "turn_off", {"entity_id": conf_enchufe})
                    return

                if is_red:
                    if 0 < val_potencia < 15:
                        data["bms_ticks"] += 1
                        if data["bms_ticks"] >= 3:
                            await hass.services.async_call("homeassistant", "turn_off", {"entity_id": conf_enchufe})
                            await hass.services.async_call("homeassistant", "turn_off", {"entity_id": sw_red})
                            await hass.services.async_call("homeassistant", "turn_off", {"entity_id": sw_solar})
                            await enviar_msg("🔋 100% Alcanzado", "Batería llena. Corriente cortada.")
                    else:
                        data["bms_ticks"] = 0
                    return

                if is_solar:
                    if val_solar < val_umbral:
                        await hass.services.async_call("homeassistant", "turn_off", {"entity_id": conf_enchufe})
                        return
                    
                    if data["energia_corte"] > 0 and val_energia >= data["energia_corte"]:
                        if not data["notificado_80"]: data["notificado_80"] = True
                        await hass.services.async_call("homeassistant", "turn_off", {"entity_id": conf_enchufe})
                        await hass.services.async_call("homeassistant", "turn_off", {"entity_id": sw_solar})
                        await enviar_msg("🔋 80% Alcanzado", "Carga Solar Finalizada.")
                        return

                    if 0 < val_potencia < 15:
                        data["bms_ticks"] += 1
                        if data["bms_ticks"] >= 3:
                            await hass.services.async_call("homeassistant", "turn_off", {"entity_id": conf_enchufe})
                            await hass.services.async_call("homeassistant", "turn_off", {"entity_id": sw_solar})
                            await enviar_msg("🔋 100% Alcanzado", "Batería llena. Corriente cortada.")
                    else:
                        data["bms_ticks"] = 0
        
            await guardar_estado()
        
        except Exception as e:
            pass

    async def event_listener(event):
        await evaluar_logica()
    
    entry.async_on_unload(hass.bus.async_listen("virtual_ev_recalc", event_listener))

    async def timer_callback(now):
        await evaluar_logica()
    
    entry.async_on_unload(async_track_time_interval(hass, timer_callback, timedelta(seconds=3)))

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    try:
        unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
        if unload_ok: hass.data[DOMAIN].pop(entry.entry_id, None)
        return unload_ok
    except Exception:
        return False
