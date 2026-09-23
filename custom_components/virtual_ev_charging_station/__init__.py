import asyncio
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
    CONF_POTENCIA, CONF_SOLAR, CONF_NOTIFICACION, CONF_CAPACIDAD,
    EFICIENCIA_CARGA, BMS_POTENCIA_MINIMA, BMS_TIEMPO_CONFIRMACION,
    POTENCIA_MAXIMA_KW, DELTA_ENERGIA_MINIMO
)

import json
import os

_LOGGER = logging.getLogger(__name__)

STORAGE_FILE = "virtual_ev_charging_station_state.json"


def _read_storage(storage_path):
    try:
        if os.path.exists(storage_path):
            with open(storage_path, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        _LOGGER.debug(f"[{DOMAIN}] No se pudo leer el almacenamiento: {e}")
    return {}


def _write_storage(storage_path, all_data):
    try:
        os.makedirs(os.path.dirname(storage_path), exist_ok=True)
        with open(storage_path, 'w', encoding='utf-8') as f:
            json.dump(all_data, f, indent=2)
    except Exception as e:
        _LOGGER.debug(f"[{DOMAIN}] No se pudo escribir el almacenamiento: {e}")


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    _LOGGER.info(f"[{DOMAIN}] Inicializando integración v1.4.0 - Reconfiguración y sensor de energía robustos")

    hass.data.setdefault(DOMAIN, {})

    data = {
        "energia_sesion": 0.0,
        "energia_objetivo": 0.0,
        "enchufe_estaba_on": False,
        "notificado_80": False,
        "notificado_ya_cargada": False,
        "bms_low_since": 0.0,
        "timestamp_encendido": 0.0,
        "energia_anterior": None,
        "energia_timestamp": 0.0,
        "energia_entidad_ref": None,
        "porcentaje_preciso": 0.0,
        "solar_sobre_umbral_desde": 0.0,
        "solar_bajo_umbral_desde": 0.0
    }

    storage_path = hass.config.path(STORAGE_DIR, STORAGE_FILE)
    entry_lock = asyncio.Lock()

    stored_data = await hass.async_add_executor_job(_read_storage, storage_path)
    if entry.entry_id in stored_data:
        data.update(stored_data[entry.entry_id])

    hass.data[DOMAIN][entry.entry_id] = data
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    conf_enchufe = entry.data.get(CONF_ENCHUFE)
    conf_energia = entry.data.get(CONF_ENERGIA)
    conf_potencia = entry.data.get(CONF_POTENCIA)
    conf_solar = entry.data.get(CONF_SOLAR)

    if not conf_enchufe: return False

    # Si se ha reconfigurado la integración con otro sensor de energía,
    # descartamos la referencia anterior: comparar el acumulado del sensor
    # nuevo contra el del antiguo generaría un salto de energía sin sentido
    # (por ejemplo, saltar al 100% de golpe al enchufar por primera vez).
    if data.get("energia_entidad_ref") != conf_energia:
        _LOGGER.info(
            f"[{DOMAIN}] Sensor de energía nuevo o distinto al guardado "
            f"({data.get('energia_entidad_ref')} -> {conf_energia}); "
            "se reinicia la referencia de energía."
        )
        data["energia_anterior"] = None
        data["energia_timestamp"] = 0.0
        data["energia_sesion"] = 0.0
        data["energia_entidad_ref"] = conf_energia

    ent_reg = er.async_get(hass)
    
    def get_real_id(dtype, name):
        eid = ent_reg.async_get_entity_id(dtype, DOMAIN, f"{entry.entry_id}_{name}")
        return eid if eid else f"{dtype}.{DOMAIN}_{name}"

    sw_solar = get_real_id("switch", "modo_automatico_solar")
    sw_red = get_real_id("switch", "forzar_carga_red")
    sw_programado = get_real_id("switch", "modo_programado")
    accion_seguir_100 = f"virtual_ev_seguir_100_{entry.entry_id}"
    time_inicio = get_real_id("time", "hora_inicio")
    num_umbral = get_real_id("number", "umbral_potencia_solar")
    num_porcentaje = get_real_id("number", "porcentaje_actual")
    num_duracion = get_real_id("number", "duracion_programada")
    num_margen_solar = get_real_id("number", "margen_estabilidad_solar")
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
            all_data = await hass.async_add_executor_job(_read_storage, storage_path)
            all_data[entry.entry_id] = data
            await hass.async_add_executor_job(_write_storage, storage_path, all_data)
        except Exception as e:
            _LOGGER.debug(f"[{DOMAIN}] No se pudo guardar el estado: {e}")

    async def enviar_msg(titulo, mensaje, extra_data=None):
        srv = entry.data.get(CONF_NOTIFICACION, "")
        if not srv: return
        try:
            parts = srv.strip().split(".")
            if len(parts) != 2: return
            payload = {"title": titulo, "message": mensaje}
            if extra_data:
                payload["data"] = extra_data
            try:
                await hass.services.async_call(parts[0], parts[1], payload)
            except Exception as e:
                if not extra_data:
                    raise
                # El servicio de notificación configurado (p.ej. Telegram) puede
                # no admitir "actions" (botones, propios de la app móvil de HA).
                # Reintentamos con el mensaje simple para no perder el aviso.
                _LOGGER.debug(f"[{DOMAIN}] Notificación con acciones rechazada, reintentando sin ellas: {e}")
                await hass.services.async_call(parts[0], parts[1], {"title": titulo, "message": mensaje})
        except Exception as e:
            _LOGGER.debug(f"[{DOMAIN}] No se pudo enviar la notificación: {e}")

    async def evaluar_logica(_=None):
        async with entry_lock:
            await _evaluar_logica_impl()

    async def _evaluar_logica_impl():
        try:
            is_on = is_state_on(conf_enchufe)
            is_red = is_state_on(sw_red)
            is_solar = is_state_on(sw_solar)
            is_programado = is_state_on(sw_programado)

            if not is_solar and not is_programado:
                # Sin ningún modo automático armado: permite que la próxima vez
                # que se active alguno, si la batería ya está al objetivo,
                # se pueda volver a avisar (en vez de quedarse silenciado para
                # siempre por un aviso de una sesión anterior).
                data["notificado_ya_cargada"] = False

            if not is_solar:
                # Sin el modo solar armado no tiene sentido arrastrar temporizadores
                # de estabilidad de una sesión anterior (evitaría el margen la
                # próxima vez que se active, disparando un encendido/apagado
                # inmediato con un valor de "desde" ya antiguo).
                data["solar_sobre_umbral_desde"] = 0.0
                data["solar_bajo_umbral_desde"] = 0.0

            val_solar = get_float(conf_solar)
            val_umbral = get_float(num_umbral, 3000.0)
            val_margen_solar = get_float(num_margen_solar, 2.0)
            val_duracion = get_float(num_duracion, 4.0)
            val_energia = get_float(conf_energia)
            val_potencia = get_float(conf_potencia)
            st_potencia = hass.states.get(conf_potencia)
            potencia_valida = st_potencia is not None and st_potencia.state not in ("unknown", "unavailable", "")
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
            st_energia = hass.states.get(conf_energia)
            energia_valida = st_energia is not None and st_energia.state not in ("unknown", "unavailable", "")

            energia_anterior = data.get("energia_anterior")
            porcentaje_actual = get_float(num_porcentaje)
            porcentaje_interno = data.get("porcentaje_preciso", porcentaje_actual)

            if abs(porcentaje_actual - round(porcentaje_interno, 1)) > 0.5:
                porcentaje_interno = porcentaje_actual

            if energia_valida:
                if energia_anterior is None or val_energia < energia_anterior:
                    # Primera lectura válida (integración nueva o recién
                    # reconfigurada con otro sensor), o contador reiniciado:
                    # muchos enchufes resetean su acumulado al conmutar el relé.
                    # En ambos casos fijamos la referencia sin aplicar ningún
                    # delta, para no interpretar el acumulado histórico del
                    # sensor como energía cargada de golpe.
                    if energia_anterior is not None:
                        _LOGGER.info(
                            f"[{DOMAIN}] El contador de energía se ha reiniciado "
                            f"({energia_anterior} -> {val_energia} kWh); se resincroniza la referencia."
                        )
                    else:
                        _LOGGER.debug(f"[{DOMAIN}] Referencia de energía inicializada a {val_energia} kWh")
                elif is_on:
                    delta_kwh = val_energia - energia_anterior
                    cap_bateria = float(entry.data.get(CONF_CAPACIDAD, 14.4))

                    # Cota física: con la potencia máxima admitida, esto es todo
                    # lo que puede haber entrado desde la lectura anterior. Filtra
                    # los valores basura que algunos enchufes publican durante la
                    # conmutación del relé, que por ser menores que la capacidad
                    # de la batería pasarían desapercibidos.
                    horas = max(0.0, ahora - data.get("energia_timestamp", 0.0)) / 3600.0
                    delta_max = max(DELTA_ENERGIA_MINIMO, POTENCIA_MAXIMA_KW * horas * 1.5)

                    if delta_kwh > delta_max:
                        _LOGGER.warning(
                            f"[{DOMAIN}] Salto de energía implausible (+{delta_kwh:.2f} kWh en {horas * 3600.0:.0f}s, "
                            f"máximo plausible {delta_max:.2f} kWh); se ignora y se resincroniza la referencia."
                        )
                    else:
                        # Energía real acumulada en esta sesión de carga. Se mide
                        # sumando deltas en vez de comparando el valor absoluto
                        # del contador contra una referencia tomada al encender:
                        # esa referencia se vuelve inservible en cuanto el
                        # contador se reinicia a mitad de carga.
                        data["energia_sesion"] = data.get("energia_sesion", 0.0) + delta_kwh

                        # Solo un 88% de lo consumido de la red llega realmente a la
                        # batería (pérdidas térmicas del cargador).
                        porcentaje_interno += (delta_kwh * EFICIENCIA_CARGA / cap_bateria) * 100.0
                        porcentaje_interno = min(100.0, porcentaje_interno)

                        nuevo_porc = round(porcentaje_interno, 1)
                        if nuevo_porc > porcentaje_actual:
                            await hass.services.async_call("number", "set_value", {
                                "entity_id": num_porcentaje,
                                "value": nuevo_porc
                            })

                # La referencia solo se mueve cuando el contador publica un valor
                # nuevo. Si se sellara la hora en cada evaluación, un contador que
                # publica cada minuto mediría su incremento contra la ventana de
                # unos segundos que separa dos evaluaciones, y la cota de plausibilidad
                # descartaría energía real.
                if val_energia != energia_anterior:
                    data["energia_anterior"] = val_energia
                    data["energia_timestamp"] = ahora

            data["porcentaje_preciso"] = porcentaje_interno

            enchufe_estaba_on = data.get("enchufe_estaba_on", False)
            
            if is_on and not enchufe_estaba_on:
                data["enchufe_estaba_on"] = True
                # El objetivo se guarda como energía a cargar en esta sesión, no
                # como una lectura absoluta del contador: así sigue siendo válido
                # aunque el contador se reinicie durante la carga.
                data["energia_sesion"] = 0.0
                data["energia_objetivo"] = val_restante
                data["notificado_80"] = False
                data["bms_low_since"] = 0.0
                data["timestamp_encendido"] = ahora
                # Al encender de verdad, cualquier temporizador de estabilidad
                # solar arrastrado de un ciclo anterior queda obsoleto.
                data["solar_sobre_umbral_desde"] = 0.0
                data["solar_bajo_umbral_desde"] = 0.0
                
                if is_red:
                    await enviar_msg("🏍️ ¡Carga en marcha! (Red)", "Conectado a la red eléctrica. Cargando la batería al 100% sin depender del sol. ⚡")
                elif is_solar:
                    await enviar_msg("☀️ ¡Aprovechando el sol!", f"Excedentes detectados ({int(val_solar)} W). Cargando la moto gratis con energía solar hasta el límite del 80% para proteger las celdas. 🌱")
                elif is_programado:
                    await enviar_msg("⏰ Carga programada iniciada", "Se ha alcanzado la hora establecida. Iniciando la carga nocturna de la moto. ⚡")

            elif not is_on and enchufe_estaba_on:
                data["enchufe_estaba_on"] = False
                data["energia_objetivo"] = 0.0
                data["energia_sesion"] = 0.0
                data["bms_low_since"] = 0.0
                data["timestamp_encendido"] = 0.0

            # REGLAS DE APAGADO
            if is_on:
                if not is_red and not is_solar and not is_programado:
                    await hass.services.async_call("homeassistant", "turn_off", {"entity_id": conf_enchufe})
                    return

                # Corte por energía al 80%: aplica tanto a solar como a
                # programado (ambos son cargas "de cortesía" que deben
                # respetar el límite saludable; solo Forzar Red se salta el
                # 80% a propósito, para llegar al 100%).
                if (is_solar or is_programado) and not is_red and data.get("energia_objetivo", 0.0) > 0 and data.get("energia_sesion", 0.0) >= data["energia_objetivo"]:
                    if not data["notificado_80"]:
                        data["notificado_80"] = True
                        await hass.services.async_call("homeassistant", "turn_off", {"entity_id": conf_enchufe})
                        if is_solar:
                            await hass.services.async_call("homeassistant", "turn_off", {"entity_id": sw_solar})
                        if is_programado:
                            await hass.services.async_call("homeassistant", "turn_off", {"entity_id": sw_programado})
                        if is_solar:
                            await enviar_msg("🔋 Objetivo solar completado", "La moto ha alcanzado el límite saludable del 80%. Enchufe desconectado automáticamente para cuidar la vida útil de tu batería. ¡Lista para rodar! 🏍️")
                        else:
                            await enviar_msg(
                                "🔋 Carga programada al 80%",
                                "Se ha alcanzado el límite saludable del 80% antes de agotar la duración programada. Enchufe desconectado. Pulsa el botón si quieres seguir cargando hasta el 100%.",
                                extra_data={
                                    # Formato de la app móvil de Home Assistant.
                                    "actions": [
                                        {"action": accion_seguir_100, "title": "⚡ Seguir hasta el 100%"}
                                    ],
                                    # Formato de notify.telegram (teclado en línea).
                                    "inline_keyboard": [
                                        f"⚡ Seguir hasta el 100%:/{accion_seguir_100}"
                                    ]
                                }
                            )
                        await guardar_estado()
                    return

                if is_solar and not is_red and val_solar < val_umbral:
                    # Margen de estabilidad: exige que la producción lleve por
                    # debajo del umbral de forma continua durante X minutos antes
                    # de cortar, para no parar y arrancar la carga con cada nube
                    # pasajera. 0 minutos = sin margen (corte instantáneo, como
                    # antes).
                    data["solar_sobre_umbral_desde"] = 0.0
                    inicio_bajo = data.get("solar_bajo_umbral_desde", 0.0)
                    if not inicio_bajo:
                        data["solar_bajo_umbral_desde"] = ahora
                    elif val_margen_solar <= 0 or (ahora - inicio_bajo) >= val_margen_solar * 60.0:
                        data["solar_bajo_umbral_desde"] = 0.0
                        await hass.services.async_call("homeassistant", "turn_off", {"entity_id": conf_enchufe})
                        return
                else:
                    data["solar_bajo_umbral_desde"] = 0.0

                tiempo_encendido = ahora - data.get("timestamp_encendido", ahora)

                # DURACIÓN DE CARGA PROGRAMADA: corte por tiempo, independiente del
                # consumo. Solo aplica en modo programado "puro" (sin red ni solar
                # activos a la vez), para no pelearse con sus propias reglas de
                # encendido/apagado. 0 horas = sin límite de duración.
                if is_programado and not is_red and not is_solar and val_duracion > 0 and tiempo_encendido >= val_duracion * 3600.0:
                    await guardar_estado()
                    await hass.services.async_call("homeassistant", "turn_off", {"entity_id": conf_enchufe})
                    await hass.services.async_call("homeassistant", "turn_off", {"entity_id": sw_programado})
                    await enviar_msg(
                        "⏰ Carga programada finalizada",
                        f"Se han completado las {val_duracion:g} horas programadas. Enchufe desconectado automáticamente."
                    )
                    return

                if (is_red or is_solar or is_programado) and tiempo_encendido > 60.0:
                    # potencia_valida evita confundir un sensor caído (unknown/
                    # unavailable, que get_float también reduce a 0.0) con un
                    # consumo real de 0W (p.ej. la moto no está enchufada).
                    if potencia_valida and val_potencia < BMS_POTENCIA_MINIMA:
                        bms_low_since = data.get("bms_low_since", 0.0)
                        if not bms_low_since:
                            data["bms_low_since"] = ahora
                        elif ahora - bms_low_since >= BMS_TIEMPO_CONFIRMACION:
                            data["bms_low_since"] = 0.0
                            await guardar_estado()

                            await hass.services.async_call("homeassistant", "turn_off", {"entity_id": conf_enchufe})
                            await hass.services.async_call("homeassistant", "turn_off", {"entity_id": sw_red})
                            await hass.services.async_call("homeassistant", "turn_off", {"entity_id": sw_solar})
                            await hass.services.async_call("homeassistant", "turn_off", {"entity_id": sw_programado})
                            await enviar_msg("🏁 Sin consumo detectado", "No se ha detectado consumo real durante 5 minutos (batería llena, moto desconectada o carga finalizada). Corriente cortada por seguridad. 🔌")
                            return
                    else:
                        data["bms_low_since"] = 0.0
                else:
                    data["bms_low_since"] = 0.0

            # REGLAS DE ENCENDIDO
            if not is_on:
                if is_red:
                    await hass.services.async_call("homeassistant", "turn_on", {"entity_id": conf_enchufe})
                    return

                # Si ya está por encima del objetivo del 80%, ni siquiera
                # encendemos el enchufe con solar/programado (Forzar Red sigue
                # pudiendo cargar hasta el 100%, por eso se comprueba antes).
                if (is_solar or is_programado) and porcentaje_actual >= 80.0:
                    # Desarmamos el/los interruptores: si no, se quedan encendidos
                    # indefinidamente "esperando" un encendido que nunca va a
                    # llegar mientras la batería siga por encima del 80%.
                    if is_solar:
                        await hass.services.async_call("homeassistant", "turn_off", {"entity_id": sw_solar})
                    if is_programado:
                        await hass.services.async_call("homeassistant", "turn_off", {"entity_id": sw_programado})
                    if not data.get("notificado_ya_cargada"):
                        data["notificado_ya_cargada"] = True
                        await enviar_msg(
                            "🔋 Batería ya al 80%",
                            f"La batería está al {porcentaje_actual:g}%, por encima del objetivo del 80%. No se activa la carga y se desarma el interruptor para proteger la batería."
                        )
                        await guardar_estado()
                    return

                if is_solar:
                    if val_solar >= val_umbral:
                        # Mismo margen de estabilidad que al apagar: exige
                        # producción por encima del umbral de forma continua
                        # durante X minutos antes de encender, para no arrancar
                        # y parar la carga con cada claro entre nubes.
                        data["solar_bajo_umbral_desde"] = 0.0
                        inicio_sobre = data.get("solar_sobre_umbral_desde", 0.0)
                        if not inicio_sobre:
                            data["solar_sobre_umbral_desde"] = ahora
                        elif val_margen_solar <= 0 or (ahora - inicio_sobre) >= val_margen_solar * 60.0:
                            data["solar_sobre_umbral_desde"] = 0.0
                            await hass.services.async_call("homeassistant", "turn_on", {"entity_id": conf_enchufe})
                            return
                    else:
                        data["solar_sobre_umbral_desde"] = 0.0

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

    entidades_a_vigilar = [sw_solar, sw_red, sw_programado, time_inicio, conf_enchufe, conf_solar, num_umbral, num_duracion, num_margen_solar]
    entry.async_on_unload(async_track_state_change_event(hass, entidades_a_vigilar, state_listener))

    async def on_notification_action(event):
        if event.data.get("action") == accion_seguir_100:
            _LOGGER.info(f"[{DOMAIN}] Acción 'Seguir hasta el 100%' pulsada desde la app móvil")
            await hass.services.async_call("homeassistant", "turn_on", {"entity_id": sw_red})

    entry.async_on_unload(hass.bus.async_listen("mobile_app_notification_action", on_notification_action))

    async def on_telegram_callback(event):
        if event.data.get("data") == f"/{accion_seguir_100}":
            _LOGGER.info(f"[{DOMAIN}] Acción 'Seguir hasta el 100%' pulsada desde Telegram")
            await hass.services.async_call("homeassistant", "turn_on", {"entity_id": sw_red})
            callback_id = event.data.get("id")
            if callback_id:
                try:
                    await hass.services.async_call("telegram_bot", "answer_callback_query", {
                        "callback_query_id": callback_id,
                        "message": "⚡ Continuando carga hasta el 100%"
                    })
                except Exception as e:
                    _LOGGER.debug(f"[{DOMAIN}] No se pudo confirmar el callback de Telegram: {e}")

    entry.async_on_unload(hass.bus.async_listen("telegram_callback", on_telegram_callback))

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


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Limpia el estado persistido cuando se elimina definitivamente la entrada."""
    storage_path = hass.config.path(STORAGE_DIR, STORAGE_FILE)
    all_data = await hass.async_add_executor_job(_read_storage, storage_path)
    if entry.entry_id in all_data:
        all_data.pop(entry.entry_id, None)
        await hass.async_add_executor_job(_write_storage, storage_path, all_data) 