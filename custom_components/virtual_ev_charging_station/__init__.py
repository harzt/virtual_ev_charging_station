import logging
from datetime import timedelta
import homeassistant.util.dt as dt_util
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_interval, async_track_state_change_event
from homeassistant.helpers.storage import STORAGE_DIR
import homeassistant.helpers.entity_registry as er
from .const import (
    DOMAIN, PLATFORMS, CONF_ENCHUFE, CONF_ENERGIA, 
    CONF_POTENCIA, CONF_SOLAR, CONF_NOTIFICACION
)

try:
    from .const import CONF_CAPACIDAD
except ImportError:
    CONF_CAPACIDAD = "capacidad_bateria"

import json
import os

_LOGGER = logging.getLogger(__name__)

STORAGE_FILE = "virtual_ev_charging_station_state.json"

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    _LOGGER.info(f"[{DOMAIN}] Inicializando integración v1.3.3 - Reloj Nativo HA")
    
    hass.data.setdefault(DOMAIN, {})
    
    data = {
        "energia_corte": 0.0,
        "enchufe_estaba_on": False,
        "notificado_80": False,
        "bms_ticks": 0,
        "timestamp_encendido": 0.0,
        "energia_anterior": 0.0,
        "porcentaje_preciso": 0.0
    }
    
    storage_path = hass.config.path(STORAGE_DIR, STORAGE_FILE)

    def _read_storage():
        try:
            if os.path.exists(storage_path):
                with open(storage_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception:
            pass
        return {}

    def _write_storage(all_data):
        try:
            os.makedirs(os.path.dirname(storage_path), exist_ok=True)
            with open(storage_path, 'w', encoding='utf-8') as f:
                json.dump(all_data, f, indent=2)
        except Exception:
            pass

    stored_data = await hass.async_add_executor_job(_read_storage)
    if entry.entry_id in stored_data:
        data.update(stored_data[entry.entry_id])
    
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
    sw_programado = get_real_id("switch", "modo_programado")
    time_inicio = get_real_id("time", "hora_inicio")
    num_umbral = get_real_id("number", "umbral_potencia_solar")
    num_porcentaje = get_real_id("number", "porcentaje_actual")
    sens_restante = get_real_id("sensor", "energia_restante_80")

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
            all_data = await hass.async_add_executor_job(_read_storage)
            all_data[entry.entry_id] = data
            await hass.async_add_executor_job(_write_storage, all_data)
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
            is_programado = is_state_on(sw_programado)

            val_solar = get_float(conf_solar)
            val_umbral = get_float(num_umbral, 3000.0)
            val_energia = get_float(conf_energia)
            val_potencia = get_float(conf_potencia)
            val_restante = get_float(sens_restante)
            st_time = hass.states.get(time_inicio)
            
            # --- SOLUCIÓN APLICADA: REEMPLAZADO time.time() POR dt_util ---
            ahora = dt_util.now().timestamp()

            if is_red or is_solar or is_programado:
                _LOGGER.warning(
                    f"\n=== DIAGNÓSTICO EV STATION ===\n"
                    f"Fuerza Red: {is_red} | Solar: {is_solar} | Reloj: {is_programado}\n"
                    f"Hora Elegida: {st_time.state if st_time else 'NO ENCONTRADA'}\n"
                    f"=============================="
                )

            # TRACKING DE BATERÍA EN TIEMPO REAL
            energia_anterior = data.get("energia_anterior", val_energia)
            porcentaje_actual = get_float(num_porcentaje)
            porcentaje_interno = data.get("porcentaje_preciso", porcentaje_actual)

            if abs(porcentaje_actual - round(porcentaje_interno, 1)) > 0.5:
                porcentaje_interno = porcentaje_actual

            if is_on and val_energia > energia_anterior:
                delta_kwh = val_energia - energia_anterior
                cap_bateria = float(entry.data.get(CONF_CAPACIDAD, 14.4))
                
                porcentaje_interno += (delta_kwh / cap_bateria) * 100.0
                porcentaje_interno = min(100.0, porcentaje_interno)
                
                nuevo_porc = round(porcentaje_interno, 1)
                if nuevo_porc > porcentaje_actual:
                    await hass.services.async_call("number", "set_value", {
                        "entity_id": num_porcentaje, 
                        "value": nuevo_porc
                    })

            data["energia_anterior"] = val_energia
            data["porcentaje_preciso"] = porcentaje_interno

            enchufe_estaba_on = data.get("enchufe_estaba_on", False)
            
            if is_on and not enchufe_estaba_on:
                data["enchufe_estaba_on"] = True
                data["energia_corte"] = val_energia + val_restante
                data["notificado_80"] = False
                data["bms_ticks"] = 0
                data["timestamp_encendido"] = ahora
                
                if is_red:
                    await enviar_msg("🏍️ ¡Carga en marcha! (Red)", "Conectado a la red eléctrica. Cargando la batería al 100% sin depender del sol. ⚡")
                elif is_solar:
                    await enviar_msg("☀️ ¡Aprovechando el sol!", f"Excedentes detectados ({int(val_solar)} W). Cargando la moto gratis con energía solar hasta el límite del 80% para proteger las celdas. 🌱")
                elif is_programado:
                    await enviar_msg("⏰ Carga programada iniciada", "Se ha alcanzado la hora establecida. Iniciando la carga nocturna de la moto. ⚡")

            elif not is_on and enchufe_estaba_on:
                data["enchufe_estaba_on"] = False
                data["energia_corte"] = 0.0
                data["bms_ticks"] = 0
                data["timestamp_encendido"] = 0.0

            # REGLAS DE APAGADO
            if is_on:
                if not is_red and not is_solar and not is_programado:
                    await hass.services.async_call("homeassistant", "turn_off", {"entity_id": conf_enchufe})
                    return

                if is_solar and not is_red and data["energia_corte"] > 0 and val_energia >= data["energia_corte"]:
                    if not data["notificado_80"]: 
                        data["notificado_80"] = True
                        await hass.services.async_call("homeassistant", "turn_off", {"entity_id": conf_enchufe})
                        await hass.services.async_call("homeassistant", "turn_off", {"entity_id": sw_solar})
                        await enviar_msg("🔋 Objetivo solar completado", "La moto ha alcanzado el límite saludable del 80%. Enchufe desconectado automáticamente para cuidar la vida útil de tu batería. ¡Lista para rodar! 🏍️")
                        await guardar_estado()
                    return

                if is_solar and not is_red and val_solar < val_umbral:
                    await hass.services.async_call("homeassistant", "turn_off", {"entity_id": conf_enchufe})
                    return

                tiempo_encendido = ahora - data.get("timestamp_encendido", ahora)
                if (is_red or is_solar or is_programado) and tiempo_encendido > 60.0:
                    if 0 < val_potencia < 15:
                        data["bms_ticks"] += 1
                        if data["bms_ticks"] >= 3:
                            data["bms_ticks"] = 0
                            await guardar_estado()
                            
                            await hass.services.async_call("homeassistant", "turn_off", {"entity_id": conf_enchufe})
                            await hass.services.async_call("homeassistant", "turn_off", {"entity_id": sw_red})
                            await hass.services.async_call("homeassistant", "turn_off", {"entity_id": sw_solar})
                            await hass.services.async_call("homeassistant", "turn_off", {"entity_id": sw_programado})
                            await enviar_msg("🏁 ¡Batería cargada al 100%!", "El cargador ha terminado de equilibrar las celdas y el consumo ha caído. Corriente cortada por seguridad. ¡Batería llena y lista para la ruta! 🚀")
                            return
                    else:
                        data["bms_ticks"] = 0
                else:
                    data["bms_ticks"] = 0

            # REGLAS DE ENCENDIDO
            if not is_on:
                if is_red:
                    await hass.services.async_call("homeassistant", "turn_on", {"entity_id": conf_enchufe})
                    return
                if is_solar and val_solar >= val_umbral:
                    await hass.services.async_call("homeassistant", "turn_on", {"entity_id": conf_enchufe})
                    return
                
                if is_programado:
                    if st_time and st_time.state not in ["unknown", "unavailable"]:
                        ahora_local_str = dt_util.now().strftime("%H:%M")
                        hora_programada_str = st_time.state[:5]
                        
                        if ahora_local_str == hora_programada_str:
                            await hass.services.async_call("homeassistant", "turn_on", {"entity_id": conf_enchufe})
                            return
        
            await guardar_estado()
        
        except Exception as e:
            _LOGGER.error(f"[{DOMAIN}] Error en evaluar_logica: {e}", exc_info=True)
            await hass.services.async_call(
                "persistent_notification", "create", 
                {
                    "message": f"La estación se ha detenido por este error: {e}", 
                    "title": "⚠️ Error EV Station"
                }
            )

    async def state_listener(event):
        await evaluar_logica()
    
    entry.async_on_unload(hass.bus.async_listen("virtual_ev_recalc", state_listener))
    
    entidades_a_vigilar = [sw_solar, sw_red, sw_programado, time_inicio, conf_enchufe, conf_solar, num_umbral]
    entry.async_on_unload(async_track_state_change_event(hass, entidades_a_vigilar, state_listener))

    async def timer_callback(now):
        await evaluar_logica()
    
    entry.async_on_unload(async_track_time_interval(hass, timer_callback, timedelta(minutes=1)))

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    try:
        unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
        if unload_ok: hass.data[DOMAIN].pop(entry.entry_id, None)
        return unload_ok
    except Exception:
        return False 