import logging
from datetime import timedelta
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import STORAGE_DIR
from .const import (
    DOMAIN, PLATFORMS, CONF_ENCHUFE, CONF_ENERGIA, 
    CONF_POTENCIA, CONF_SOLAR, CONF_NOTIFICACION
)
import json
import os

_LOGGER = logging.getLogger(__name__)

# Archivo de persistencia
STORAGE_FILE = "virtual_ev_charging_station_state.json"

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Configuración principal de la integración."""
    _LOGGER.info(f"[{DOMAIN}] Inicializando integración v1.1.0")
    
    hass.data.setdefault(DOMAIN, {})
    
    # Datos persistentes y en memoria
    data = {
        "energia_corte": 0.0,
        "enchufe_estaba_on": False,
        "notificado_80": False,
        "bms_ticks": 0,
        "timestamp_ultimo_apagado": None,
    }
    
    # Cargar estado persistente desde almacenamiento
    storage_path = hass.config.path(STORAGE_DIR, STORAGE_FILE)
    try:
        if os.path.exists(storage_path):
            with open(storage_path, 'r', encoding='utf-8') as f:
                stored_data = json.load(f)
                if entry.entry_id in stored_data:
                    data.update(stored_data[entry.entry_id])
                    _LOGGER.debug(f"[{DOMAIN}] Estado restaurado desde almacenamiento: {data}")
    except Exception as e:
        _LOGGER.warning(f"[{DOMAIN}] No se pudo cargar estado persistente: {e}")
    
    hass.data[DOMAIN][entry.entry_id] = data

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    conf_enchufe = entry.data.get(CONF_ENCHUFE)
    conf_energia = entry.data.get(CONF_ENERGIA)
    conf_potencia = entry.data.get(CONF_POTENCIA)
    conf_solar = entry.data.get(CONF_SOLAR)

    # Validación crítica de configuración
    if not conf_enchufe:
        _LOGGER.error(f"[{DOMAIN}] Error crítico: No hay enchufe configurado.")
        return False
    
    if not all([conf_energia, conf_potencia, conf_solar]):
        _LOGGER.error(f"[{DOMAIN}] Error crítico: Faltan sensores requeridos. Energía: {conf_energia}, Potencia: {conf_potencia}, Solar: {conf_solar}")
        return False

    sw_solar = f"switch.{DOMAIN}_modo_automatico_solar"
    sw_red = f"switch.{DOMAIN}_forzar_carga_red"
    num_umbral = f"number.{DOMAIN}_umbral_potencia_solar"
    sens_restante = f"sensor.{DOMAIN}_energia_restante_80"

    def get_float(eid, default=0.0):
        """Conversor Blindado: Resuelve el fallo de los 6575.0W europeos"""
        try:
            st = hass.states.get(eid)
            if not st or st.state in ["unknown", "unavailable", ""]:
                _LOGGER.debug(f"[{DOMAIN}] Entidad {eid} no disponible, usando default: {default}")
                return default
            
            try:
                # 1. Quitar letras o espacios (ej. "6575 W" -> "6575")
                s = str(st.state).strip().replace('W', '').replace('w', '').replace(' ', '')
                # 2. Arreglar las comas y puntos de miles europeos ("6.575,0" -> "6575.0")
                s = s.replace(',', '.')
                parts = s.split('.')
                if len(parts) > 2:
                    s = ''.join(parts[:-1]) + '.' + parts[-1]
                
                val = float(s)
                
                # 3. Ajuste de kW a W si es necesario
                uom = st.attributes.get("unit_of_measurement", "").lower()
                if "kw" in uom and "kwh" not in uom: val *= 1000.0
                if uom == "wh": val /= 1000.0
                
                _LOGGER.debug(f"[{DOMAIN}] Convertido {eid}: '{st.state}' → {val} (UOM: {uom})")
                return val
            except ValueError as ve:
                _LOGGER.warning(f"[{DOMAIN}] Error al parsear valor de {eid}: '{st.state}' - {ve}")
                return default
        except Exception as e:
            _LOGGER.error(f"[{DOMAIN}] Error inesperado en get_float({eid}): {e}")
            return default

    async def guardar_estado():
        """Persiste el estado en almacenamiento."""
        try:
            storage_path = hass.config.path(STORAGE_DIR, STORAGE_FILE)
            os.makedirs(os.path.dirname(storage_path), exist_ok=True)
            
            all_data = {}
            try:
                if os.path.exists(storage_path):
                    with open(storage_path, 'r', encoding='utf-8') as f:
                        all_data = json.load(f)
            except:
                pass
            
            all_data[entry.entry_id] = data
            
            with open(storage_path, 'w', encoding='utf-8') as f:
                json.dump(all_data, f, indent=2)
            
            _LOGGER.debug(f"[{DOMAIN}] Estado guardado: {data}")
        except Exception as e:
            _LOGGER.error(f"[{DOMAIN}] Error guardando estado persistente: {e}")

    async def enviar_msg(titulo, mensaje):
        """Envía notificación si está configurada."""
        srv = entry.data.get(CONF_NOTIFICACION, "")
        if not srv:
            _LOGGER.debug(f"[{DOMAIN}] No hay servicio de notificación configurado")
            return
        try:
            parts = srv.strip().split(".")
            if len(parts) != 2:
                _LOGGER.warning(f"[{DOMAIN}] Formato de notificación inválido: {srv}")
                return
            
            await hass.services.async_call(parts[0], parts[1], {"title": titulo, "message": mensaje})
            _LOGGER.info(f"[{DOMAIN}] Notificación enviada: {titulo} - {mensaje}")
        except Exception as e:
            _LOGGER.error(f"[{DOMAIN}] Error enviando notificación: {e}")

    async def evaluar_logica(_=None):
        """Lógica principal de decisión."""
        try:
            is_on = hass.states.is_on(conf_enchufe)
            is_red = hass.states.is_on(sw_red)
            is_solar = hass.states.is_on(sw_solar)

            val_solar = get_float(conf_solar)
            val_umbral = get_float(num_umbral, 3000.0)
            val_energia = get_float(conf_energia)
            val_potencia = get_float(conf_potencia)
            val_restante = get_float(sens_restante)

            _LOGGER.debug(
                f"[{DOMAIN}] Estado: on={is_on}, red={is_red}, solar={is_solar} | "
                f"Solar={val_solar}W, Umbral={val_umbral}W, Energía={val_energia}kWh, "
                f"Potencia={val_potencia}kW, Restante={val_restante}kWh"
            )

            # SI LA CARGA ACABA DE INICIAR
            if is_on and not data["enchufe_estaba_on"]:
                data["energia_corte"] = val_energia + val_restante
                data["notificado_80"] = False
                data["bms_ticks"] = 0
                _LOGGER.info(f"[{DOMAIN}] ⚡ CARGA INICIADA - Objetivo energético: {data['energia_corte']:.2f} kWh")
                
                if is_red or is_solar:
                    msg = "Carga por Red (100%)." if is_red else "Carga Solar (80%)."
                    await enviar_msg("⚡ Moto Cargando", msg)

            # SI LA CARGA ACABA DE TERMINAR
            elif not is_on and data["enchufe_estaba_on"]:
                _LOGGER.info(f"[{DOMAIN}] 🔌 CARGA DETENIDA")
                data["energia_corte"] = 0.0
                data["bms_ticks"] = 0

            data["enchufe_estaba_on"] = is_on

            # REGLAS DE ENCENDIDO IMPLACABLES
            if not is_on:
                if is_red:
                    _LOGGER.info(f"[{DOMAIN}] 🔌 Activando carga por Red...")
                    await hass.services.async_call("homeassistant", "turn_on", {"entity_id": conf_enchufe})
                    return
                
                if is_solar and val_solar >= val_umbral:
                    _LOGGER.info(f"[{DOMAIN}] ☀️ Activando carga Solar (Producción {val_solar}W >= Umbral {val_umbral}W)")
                    await hass.services.async_call("homeassistant", "turn_on", {"entity_id": conf_enchufe})
                    return

            # REGLAS DE APAGADO
            if is_on:
                if is_red:
                    # Modo Red: Detectar fin de carga por caída de consumo
                    if 0 < val_potencia < 15:
                        data["bms_ticks"] += 1
                        _LOGGER.debug(f"[{DOMAIN}] 🔋 BMS Tick (Red): {data['bms_ticks']}/3 - Potencia baja: {val_potencia}kW")
                        
                        if data["bms_ticks"] >= 3:
                            _LOGGER.warning(f"[{DOMAIN}] 🔋 Batería detectada LLENA (100%) - Apagando enchufe")
                            await hass.services.async_call("homeassistant", "turn_off", {"entity_id": conf_enchufe})
                            await hass.services.async_call("homeassistant", "turn_off", {"entity_id": sw_red})
                            await hass.services.async_call("homeassistant", "turn_off", {"entity_id": sw_solar})
                            await enviar_msg("🔋 100% Alcanzado", "Batería llena. Corriente cortada.")
                    else:
                        data["bms_ticks"] = 0
                    return

                if is_solar:
                    # Cae el sol
                    if val_solar < val_umbral:
                        _LOGGER.info(f"[{DOMAIN}] 🌙 Producción solar insuficiente ({val_solar}W < {val_umbral}W) - Apagando enchufe")
                        await hass.services.async_call("homeassistant", "turn_off", {"entity_id": conf_enchufe})
                        return
                    
                    # Llega al 80% de energía
                    if data["energia_corte"] > 0 and val_energia >= data["energia_corte"]:
                        if not data["notificado_80"]:
                            _LOGGER.info(f"[{DOMAIN}] 🔋 Objetivo al 80% alcanzado ({val_energia:.2f}kWh >= {data['energia_corte']:.2f}kWh)")
                            data["notificado_80"] = True
                        
                        await hass.services.async_call("homeassistant", "turn_off", {"entity_id": conf_enchufe})
                        await hass.services.async_call("homeassistant", "turn_off", {"entity_id": sw_solar})
                        await enviar_msg("🔋 80% Alcanzado", "Carga Solar Finalizada.")
                        return

                    # Batería llena (redundancia de seguridad)
                    if 0 < val_potencia < 15:
                        data["bms_ticks"] += 1
                        _LOGGER.debug(f"[{DOMAIN}] 🔋 BMS Tick (Solar): {data['bms_ticks']}/3 - Potencia baja: {val_potencia}kW")
                        
                        if data["bms_ticks"] >= 3:
                            _LOGGER.warning(f"[{DOMAIN}] 🔋 Batería detectada LLENA (100%) en modo Solar - Apagando")
                            await hass.services.async_call("homeassistant", "turn_off", {"entity_id": conf_enchufe})
                            await hass.services.async_call("homeassistant", "turn_off", {"entity_id": sw_solar})
                            await enviar_msg("🔋 100% Alcanzado", "Batería llena. Corriente cortada.")
                    else:
                        data["bms_ticks"] = 0
            
            # Guardar estado después de cambios importantes
            await guardar_estado()
            
        except Exception as e:
            _LOGGER.error(f"[{DOMAIN}] Error crítico en evaluar_logica: {e}", exc_info=True)

    # Escucha instantánea si pulsas los botones
    async def event_listener(event):
        """Listener para eventos de recálculo."""
        _LOGGER.debug(f"[{DOMAIN}] Evento recibido: {event.event_type}")
        await evaluar_logica()
    
    entry.async_on_unload(hass.bus.async_listen("virtual_ev_recalc", event_listener))

    # Bucle de seguridad de 3 segundos que lee la placa solar y nunca se atasca
    async def timer_callback(now):
        """Callback periódico del timer de seguridad."""
        await evaluar_logica()
    
    entry.async_on_unload(async_track_time_interval(hass, timer_callback, timedelta(seconds=3)))

    _LOGGER.info(f"[{DOMAIN}] ✅ Integración inicializada correctamente")
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Descarga la integración."""
    _LOGGER.info(f"[{DOMAIN}] Descargando integración...")
    try:
        unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
        if unload_ok:
            hass.data[DOMAIN].pop(entry.entry_id, None)
            _LOGGER.info(f"[{DOMAIN}] Integración descargada correctamente")
        return unload_ok
    except Exception as e:
        _LOGGER.error(f"[{DOMAIN}] Error descargando integración: {e}")
        return False
