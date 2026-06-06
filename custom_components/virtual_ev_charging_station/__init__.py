from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_state_change_event, async_call_later
from .const import DOMAIN, PLATFORMS, CONF_ENCHUFE, CONF_ENERGIA, CONF_POTENCIA, CONF_SOLAR, CONF_NOTIFICACION

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Configura Virtual EV charging station e inicia la automatización nativa."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "energia_corte": 0.0,
        "sensor_corte": None,
        "bms_timer_cancel": None,
        "has_notified_80": False
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    conf_enchufe = entry.data[CONF_ENCHUFE]
    conf_energia = entry.data[CONF_ENERGIA]
    conf_potencia = entry.data[CONF_POTENCIA]
    conf_solar = entry.data[CONF_SOLAR]
    
    # Función de apoyo dinámica para notificaciones
    async def enviar_notificacion(titulo, mensaje):
        servicio = entry.data.get(CONF_NOTIFICACION, "").strip()
        if servicio:
            # Soporta tanto "notify.telegram_kiko" como "telegram_kiko" a secas
            partes = servicio.split(".")
            if len(partes) == 2:
                await hass.services.async_call(partes[0], partes[1], {"title": titulo, "message": mensaje})
            else:
                await hass.services.async_call("notify", servicio, {"title": titulo, "message": mensaje})

    async def _handle_state_change(event):
        entity_id = event.data.get("entity_id")
        new_state = event.data.get("new_state")
        old_state = event.data.get("old_state")

        if not new_state:
            return

        # 1. Reset al cambiar el porcentaje manual
        if entity_id == f"number.{DOMAIN}_porcentaje_actual":
            if old_state and new_state.state != old_state.state:
                hass.data[DOMAIN][entry.entry_id]["energia_corte"] = 0.0
                hass.data[DOMAIN][entry.entry_id]["has_notified_80"] = False
                if hass.data[DOMAIN][entry.entry_id]["sensor_corte"]:
                    hass.data[DOMAIN][entry.entry_id]["sensor_corte"].update_value(0.0)

        # 2. Inicio del enchufe físico (Fijar lecturas iniciales y corte)
        elif entity_id == conf_enchufe:
            if new_state.state == "on" and (not old_state or old_state.state != "on"):
                if hass.data[DOMAIN][entry.entry_id]["energia_corte"] == 0.0:
                    lectura_actual = float(hass.states.get(conf_energia).state or 0.0) if hass.states.get(conf_energia) else 0.0
                    necesarios_state = hass.states.get(f"sensor.{DOMAIN}_energia_restante_80")
                    necesarios = float(necesarios_state.state or 0.0) if necesarios_state and necesarios_state.state not in ["unknown", "unavailable"] else 0.0
                    
                    new_corte = lectura_actual + necesarios
                    hass.data[DOMAIN][entry.entry_id]["energia_corte"] = new_corte
                    if hass.data[DOMAIN][entry.entry_id]["sensor_corte"]:
                        hass.data[DOMAIN][entry.entry_id]["sensor_corte"].update_value(new_corte)

                    forzar_red = hass.states.is_on(f"switch.{DOMAIN}_forzar_carga_red")
                    tiempo_state = hass.states.get(f"sensor.{DOMAIN}_tiempo_restante")
                    tiempo = tiempo_state.state if tiempo_state else "0m"

                    msg = "Cargador forzado desde la Red. Objetivo final: 100% de batería." if forzar_red else f"Cargador activado por excedentes solares. Tiempo neto estimado al 80%: {tiempo}."
                    await enviar_notificacion("⚡ *Carga de Moto Iniciada*", msg)
            
            elif new_state.state == "off":
                if hass.data[DOMAIN][entry.entry_id]["bms_timer_cancel"]:
                    hass.data[DOMAIN][entry.entry_id]["bms_timer_cancel"]()
                    hass.data[DOMAIN][entry.entry_id]["bms_timer_cancel"] = None

        # 3 y 4. Gestión por Excedentes Solares
        elif entity_id in [conf_solar, f"number.{DOMAIN}_umbral_potencia_solar"]:
            solar_state = hass.states.get(conf_solar)
            solar_power = float(solar_state.state) if solar_state and solar_state.state not in ["unknown", "unavailable"] else 0.0
            
            umbral_state = hass.states.get(f"number.{DOMAIN}_umbral_potencia_solar")
            umbral = float(umbral_state.state) if umbral_state and umbral_state.state not in ["unknown", "unavailable"] else 3000.0

            modo_solar = hass.states.is_on(f"switch.{DOMAIN}_modo_automatico_solar")
            enchufe_on = hass.states.is_on(conf_enchufe)
            forzar_red = hass.states.is_on(f"switch.{DOMAIN}_forzar_carga_red")

            if solar_power >= umbral and modo_solar and not enchufe_on:
                await hass.services.async_call("switch", "turn_on", {"entity_id": conf_enchufe})
            elif solar_power < umbral and enchufe_on and not forzar_red:
                await hass.services.async_call("switch", "turn_off", {"entity_id": conf_enchufe})

        # 5 y 6. Gestión de Carga Forzada por Red
        elif entity_id == f"switch.{DOMAIN}_forzar_carga_red":
            if old_state and new_state.state != old_state.state:
                enchufe_on = hass.states.is_on(conf_enchufe)
                if new_state.state == "on" and not enchufe_on:
                    await hass.services.async_call("switch", "turn_on", {"entity_id": conf_enchufe})
                elif new_state.state == "off" and enchufe_on:
                    solar_state = hass.states.get(conf_solar)
                    solar_power = float(solar_state.state or 0.0) if solar_state and solar_state.state not in ["unknown", "unavailable"] else 0.0
                    
                    umbral_state = hass.states.get(f"number.{DOMAIN}_umbral_potencia_solar")
                    umbral = float(umbral_state.state) if umbral_state and umbral_state.state not in ["unknown", "unavailable"] else 3000.0

                    if solar_power < umbral:
                        await hass.services.async_call("switch", "turn_off", {"entity_id": conf_enchufe})

        # 7. Monitoreo del consumo de energía y corte al 80%
        elif entity_id == conf_energia:
            if new_state.state not in ["unknown", "unavailable"]:
                current_energy = float(new_state.state)
                corte = hass.data[DOMAIN][entry.entry_id]["energia_corte"]
                enchufe_on = hass.states.is_on(conf_enchufe)

                if corte > 0.0 and current_energy >= corte and enchufe_on:
                    forzar_red = hass.states.is_on(f"switch.{DOMAIN}_forzar_carga_red")
                    if not forzar_red:
                        await hass.services.async_call("switch", "turn_off", {"entity_id": conf_enchufe})
                        await hass.services.async_call("switch", "turn_off", {"entity_id": f"switch.{DOMAIN}_modo_automatico_solar"})
                        hass.data[DOMAIN][entry.entry_id]["energia_corte"] = 0.0
                        if hass.data[DOMAIN][entry.entry_id]["sensor_corte"]:
                            hass.data[DOMAIN][entry.entry_id]["sensor_corte"].update_value(0.0)
                        await enviar_notificacion("🔋 *Carga al 80% Completada*", "El enchufe se ha apagado automáticamente tras consumir la energía estimada en modo Solar.")
                    else:
                        if not hass.data[DOMAIN][entry.entry_id]["has_notified_80"]:
                            hass.data[DOMAIN][entry.entry_id]["has_notified_80"] = True
                            await enviar_notificacion("⏳ *Moto al 80% (Modo Red)*", "Se ha alcanzado el 80% de carga estimada. El proceso continúa adelante hasta llenar el 100% de la batería.")

        # 8. Monitoreo de potencia baja (Corte por BMS / Moto desconectada)
        elif entity_id == conf_potencia:
            if new_state.state not in ["unknown", "unavailable"]:
                power = float(new_state.state)
                enchufe_on = hass.states.is_on(conf_enchufe)

                if power < 15 and enchufe_on:
                    if hass.data[DOMAIN][entry.entry_id]["bms_timer_cancel"] is None:
                        def _bms_cutoff_action(_):
                            hass.data[DOMAIN][entry.entry_id]["bms_timer_cancel"] = None
                            hass.async_create_task(hass.services.async_call("switch", "turn_off", {"entity_id": conf_enchufe}))
                            hass.async_create_task(hass.services.async_call("switch", "turn_off", {"entity_id": f"switch.{DOMAIN}_forzar_carga_red"}))
                            hass.async_create_task(hass.services.async_call("switch", "turn_off", {"entity_id": f"switch.{DOMAIN}_modo_automatico_solar"}))
                            hass.data[DOMAIN][entry.entry_id]["energia_corte"] = 0.0
                            if hass.data[DOMAIN][entry.entry_id]["sensor_corte"]:
                                hass.data[DOMAIN][entry.entry_id]["sensor_corte"].update_value(0.0)
                            
                            # Uso del nuevo sistema de notificaciones dinámico
                            hass.async_create_task(enviar_notificacion("🔋 *Carga al 100% Completada*", "El enchufe se ha apagado tras detectar un consumo mínimo (Batería llena o moto desconectada)."))
                        
                        hass.data[DOMAIN][entry.entry_id]["bms_timer_cancel"] = async_call_later(hass, 300, _bms_cutoff_action)
                else:
                    if hass.data[DOMAIN][entry.entry_id]["bms_timer_cancel"]:
                        hass.data[DOMAIN][entry.entry_id]["bms_timer_cancel"]()
                        hass.data[DOMAIN][entry.entry_id]["bms_timer_cancel"] = None

        hass.bus.async_fire(f"{DOMAIN}_update_sensors")

    tracked_entities = [
        f"number.{DOMAIN}_porcentaje_actual",
        f"number.{DOMAIN}_umbral_potencia_solar",
        f"switch.{DOMAIN}_forzar_carga_red",
        conf_enchufe,
        conf_solar,
        conf_energia,
        conf_potencia
    ]
    entry.async_on_unload(async_track_state_change_event(hass, tracked_entities, _handle_state_change))

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Descarga la integración."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        if hass.data[DOMAIN][entry.entry_id]["bms_timer_cancel"]:
            hass.data[DOMAIN][entry.entry_id]["bms_timer_cancel"]()
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
