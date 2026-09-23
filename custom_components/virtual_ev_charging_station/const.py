DOMAIN = "virtual_ev_charging_station"
PLATFORMS = ["switch", "number", "sensor", "time"]

# Las variables exactas introducidas en la configuración (config_flow)
CONF_ENCHUFE = "enchufe_switch"
CONF_ENERGIA = "enchufe_energia"
CONF_POTENCIA = "enchufe_potencia"
CONF_SOLAR = "sensor_solar"
CONF_CAPACIDAD = "capacidad_bateria"
CONF_EFICIENCIA = "eficiencia_carga"
CONF_POTENCIA_CARGA = "potencia_carga"
CONF_UMBRAL_SOLAR = "umbral_solar"
CONF_NOTIFICACION = "servicio_notificacion"

# Rendimiento del cargador (pérdidas térmicas): porcentaje de lo consumido de la
# red que llega realmente a la batería. Es solo el valor por defecto: cada
# instalación lo ajusta en la configuración, porque depende del cargador y
# porque absorbe también la falta de linealidad entre los kWh reales y el
# porcentaje que muestra el BMS del vehículo.
EFICIENCIA_CARGA_DEFECTO = 88.0


def eficiencia(entry):
    """Rendimiento configurado, como fracción (0-1)."""
    try:
        valor = float(str(entry.data.get(CONF_EFICIENCIA, EFICIENCIA_CARGA_DEFECTO)).replace(',', '.'))
    except (ValueError, TypeError):
        valor = EFICIENCIA_CARGA_DEFECTO
    if not 0 < valor <= 100:
        valor = EFICIENCIA_CARGA_DEFECTO
    return valor / 100.0

# Umbral y tiempo de espera para la detección de fin de carga por el BMS
BMS_POTENCIA_MINIMA = 15.0
BMS_TIEMPO_CONFIRMACION = 300.0  # 5 minutos

# Potencia máxima admitida por el slider de carga. Se usa para acotar cuánta
# energía puede haber entrado como mucho entre dos lecturas y descartar así los
# valores basura que algunos enchufes publican al conmutar el relé.
POTENCIA_MAXIMA_KW = 11.0

# Suelo del margen anterior, en kWh: la resolución típica de estos contadores es
# de 0.01 kWh y las evaluaciones pueden ir separadas por pocos segundos, así que
# un incremento pequeño siempre debe considerarse válido.
DELTA_ENERGIA_MINIMO = 0.05