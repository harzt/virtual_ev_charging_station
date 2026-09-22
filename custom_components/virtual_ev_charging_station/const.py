DOMAIN = "virtual_ev_charging_station"
PLATFORMS = ["switch", "number", "sensor", "time"]

# Las variables exactas introducidas en la configuración (config_flow)
CONF_ENCHUFE = "enchufe_switch"
CONF_ENERGIA = "enchufe_energia"
CONF_POTENCIA = "enchufe_potencia"
CONF_SOLAR = "sensor_solar"
CONF_CAPACIDAD = "capacidad_bateria"
CONF_POTENCIA_CARGA = "potencia_carga"
CONF_UMBRAL_SOLAR = "umbral_solar"
CONF_NOTIFICACION = "servicio_notificacion"

# Rendimiento estimado del cargador (pérdidas térmicas): 88% de lo consumido
# de la red llega realmente a la batería.
EFICIENCIA_CARGA = 0.88

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