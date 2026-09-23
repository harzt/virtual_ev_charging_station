# Virtual EV Charging Station 🚗⚡

**Virtual EV Charging Station** es una integración personalizada para Home Assistant que convierte cualquier enchufe inteligente con medición de consumo en un cargador inteligente virtual para tu vehículo eléctrico o moto. 

Está diseñada especialmente para vehículos sin conectividad nativa (API), permitiendo proteger la vida útil de su batería mediante paradas automáticas al **80%** calculadas por software, optimización de excedentes fotovoltaicos y carga forzada desde la red eléctrica.

---

## 🚀 Características principales

* **Cálculo dinámico por energía (kWh):** Olvídate del tiempo fijo. La integración mide los kWh reales extraídos del enchufe para clavar la parada al 80%.
* **Cuenta atrás en tiempo real:** Sensores dinámicos de energía restante y tiempo estimado que decrecen minuto a minuto durante la carga.
* **Gestión de Excedentes Solares:** Arranca y pausa la carga automáticamente según la producción de tus placas solares y el umbral ajustable que elijas.
* **Memoria inteligente contra nubes:** Si una nube apaga el cargador, el sistema retiene el objetivo original y reanuda el conteo exacto al volver el sol.
* **Margen de estabilidad ante nubes intermitentes:** El control **Margen Estabilidad Solar** (minutos, 0 = desactivado) exige que la producción se mantenga de forma continua por encima o por debajo del umbral durante ese tiempo antes de encender o apagar, evitando que el enchufe arranque y pare repetidamente en días de nubes pasajeras.
* **Modo Forzar Red al 100% (BMS):** Carga continua sin importar el sol. Al llegar al 100%, detecta la caída de consumo del Sistema de Gestión de Batería (BMS) de tu vehículo y corta el enchufe por seguridad.
* **Carga Programada con duración ajustable:** Define la hora de inicio y cuántas horas quieres que cargue (control **Duración Carga Programada**, en horas). El corte al 80% (por kWh reales) también aplica a este modo, y la duración actúa como límite máximo de seguridad si no llega a alcanzarlo antes.
* **Protección contra cargas innecesarias:** Si activas Carga Automática Solar o Carga Programada y la batería ya está por encima del 80%, la integración no enciende el enchufe y te avisa por notificación en vez de encender y apagar el relé sin necesidad.
* **Notificación accionable al llegar al 80% en modo programado:** El aviso de corte al 80% en Carga Programada incluye un botón "⚡ Seguir hasta el 100%" que activa **Forzar Carga desde Red** sin tener que abrir el panel. Funciona tanto con la app móvil de Home Assistant como con Telegram (teclado en línea); con otros servicios de notificación se envía el mismo aviso sin el botón.

---

## ⚙️ ¿Cómo funciona internamente?

La integración opera de forma completamente autónoma en el núcleo de Home Assistant bajo la siguiente lógica:

1. **Planificación:** Al ajustar el **Porcentaje Actual** de tu vehículo y la **Potencia de Carga**, el sistema calcula instantáneamente cuántos kWh netos faltan para el objetivo aplicando el **Rendimiento del Cargador** que hayas configurado (88% por defecto: las pérdidas térmicas hacen que no toda la energía de red llegue a la batería).

    > 💡 **Cómo calibrarlo:** tras una carga completa, compara el porcentaje que marca tu vehículo con el que muestra la integración. Si el vehículo marca **más** de lo previsto, sube el rendimiento; si marca **menos**, bájalo. Este parámetro absorbe además la falta de linealidad entre los kWh reales y el porcentaje que muestra el BMS, así que no tiene por qué coincidir con la eficiencia de catálogo del cargador.
2. **Activación de Carga:** En cuanto el enchufe se enciende (vía Sol o vía Red), la integración fija los kWh que faltan como **objetivo de la sesión** y va acumulando la energía realmente inyectada sumando los incrementos de tu contador. Al medir por incrementos en lugar de por valor absoluto, el corte sigue siendo exacto aunque el contador del enchufe se reinicie a mitad de carga (algo habitual en enchufes que resetean su acumulado al conmutar el relé).
3. **Control Solar:** Monitorea tu producción fotovoltaica. Si supera el umbral configurado por el usuario, el enchufe se activa. Si cae, se apaga (salvo que la carga por red esté activa).
4. **Protección BMS:** Si estás cargando en modo Red hacia el 100%, un temporizador interno vigila la potencia. Si el consumo cae por debajo de **15W durante 5 minutos seguidos**, el enchufe se apaga asumiendo carga completa o desconexión física.

---

## 📦 Instalación y Configuración

### 1. Componente Base (Backend)
1. Copia la carpeta `virtual_ev_charging_station` dentro del directorio `custom_components/` de tu Home Assistant.
2. Reinicia Home Assistant.
3. Ve a **Ajustes > Dispositivos y servicios > Añadir integración** y busca `Virtual EV charging station`.
4. Completa el formulario con tus entidades reales (enchufe, sensores de potencia/energía y sensor solar).

### 2. Panel de Control Visual (¡Imprescindible!) 🎴
Para controlar este sistema de forma interactiva y fluida sin lidiar con infinitas tarjetas de entidades nativas, instala su tarjeta compañera desde HACS Frontend:

👉 **[Virtual EV Charging Card](https://github.com/harzt/virtual-ev-charging-card)**

Esta tarjeta te permitirá deslizar el porcentaje de batería y la potencia, conmutar los modos de carga y ver animaciones de flujo energético en tiempo real directamente desde tu Dashboard con una sola línea de código:

```yaml
type: custom:virtual-ev-charging-card
```
## 📝 Ejemplos Prácticos de Uso Diario

> 💡 **Parámetros de partida para los ejemplos:** Vehículo con batería de **13 kWh** cargando en un enchufe inteligente limitado a **1.4 kW** (rendimiento configurado al 88%).

---

### ☀️ Escenario A: Carga con Excedentes Solares (Corte automático al 80%)

Este modo está diseñado para el día a día, optimizando tu producción fotovoltaica y evitando el estrés que sufre la batería al pasar largas horas degradándose al 100%.

* **10:00 AM | Preparación:** Llegas a casa con la moto al **20%** de batería y la dejas enchufada. Abres tu panel y deslizas el indicador a `20%`. 
    * *El sistema calcula:* Energía requerida al 80% = **8.86 kWh** | Tiempo estimado = **6h 20m**.
* **10:05 AM | Armado:** Activas el interruptor **Modo Automático Solar** (el umbral de arranque está fijado en tu tarjeta a `3000W`). El cargador sigue apagado.
* **11:30 AM | Arranque Solar:** Tu producción fotovoltaica sube a **3200W**. La integración activa el enchufe automáticamente y te envía un Telegram:
    > ⚡ **Carga de Moto Iniciada:** Cargador activado por excedentes solares. Tiempo neto estimado al 80%: 6h 20m.
* **01:45 PM | Paso de Nube (Pausa):** El cielo se cubre y la producción cae a **1800W**. El enchufe se apaga solo. El sistema guarda en su memoria interna que ya han entrado **3.50 kWh** limpios.
* **02:15 PM | Reanudación:** Vuelve a salir el sol (>3000W). El enchufe se enciende de nuevo. El sensor dinámico descuenta lo cargado y marca que ahora restan **5.36 kWh** y **3h 50m** de cuenta atrás.
* **06:05 PM | Fin de Carga:** El contador de energía del enchufe confirma que se han completado los **8.86 kWh** totales desde el inicio. La integración apaga el enchufe de golpe, desarma el interruptor solar para el día siguiente y te avisa:
    > 🔋 **Carga al 80% Completada:** El enchufe se ha apagado automáticamente tras consumir la energía estimada en modo Solar.

---

### 🔌 Escenario B: Carga de Emergencia (Forzar Red al 100%)

Ideal para cuando necesitas exprimir la autonomía máxima del vehículo porque tienes previsto realizar un viaje largo al día siguiente. En este modo el 80% no se tiene en cuenta en ningún momento: el objetivo es siempre el 100%, sin pausas ni avisos intermedios.

* **09:00 PM | Activación:** Conectas la moto al garaje y enciendes el interruptor **Forzar Carga desde Red**.
* **09:01 PM | Arranque Inmediato:** El cargador se activa en el acto ignorando por completo que ya es de noche, que no hay sol y cuál sea el porcentaje actual de la batería:
    > ⚡ **Carga de Moto Iniciada:** Cargador forzado desde la Red. Objetivo final: 100% de batería.
* **04:45 AM | Actuación del BMS:** La batería llega a su límite real del 100%. El sistema de gestión interna de la moto (BMS) reduce drásticamente la potencia para equilibrar las celdas.
* **04:50 AM | Apagado por Seguridad:** Tras registrar que la potencia de carga lleva **5 minutos seguidos por debajo de 15W**, la integración asume que el proceso ha terminado. Apaga el enchufe para proteger el transformador, desactiva el botón de Red y te envía el reporte final:
    > 🔋 **Carga al 100% Completada:** El enchufe se ha apagado tras detectar un consumo mínimo (Batería llena o moto desconectada).

---

### ⏰ Escenario C: Carga Programada Nocturna (corte al 80% con opción de seguir al 100%)

Perfecto para cargar de noche (por ejemplo, a tarifa valle) sin tener que acordarte de nada ni vigilar el proceso.

* **10:00 PM | Preparación:** Llegas a casa con la moto al **30%** y la dejas enchufada. Ajustas la **Hora de Inicio Programada** a `03:00`, dejas la **Duración Carga Programada** en `4h` (como límite de seguridad) y activas el interruptor **Carga Programada Horaria**. El cargador sigue apagado hasta que llegue la hora.
* **03:00 AM | Arranque programado:** Se cumple la hora fijada y la integración enciende el enchufe automáticamente:
    > ⏰ **Carga programada iniciada:** Se ha alcanzado la hora establecida. Iniciando la carga nocturna de la moto. ⚡
* **06:40 AM | Corte al 80%:** El contador de energía confirma que se han completado los kWh reales necesarios para el 80%, bastante antes de agotar las 4 horas de margen. El enchufe se apaga y el interruptor de programación se desarma. Te llega un aviso con un botón de acción (Telegram o app móvil):
    > 🔋 **Carga programada al 80%:** Se ha alcanzado el límite saludable del 80%. Enchufe desconectado. Pulsa el botón si quieres seguir cargando hasta el 100%.
    > **[⚡ Seguir hasta el 100%]**
* **06:41 AM | (Opcional) Seguir hasta el 100%:** Pulsas el botón desde Telegram o la app móvil sin necesidad de abrir el panel. La integración activa **Forzar Carga desde Red** al instante y la carga continúa hasta el 100%, con el mismo corte final por BMS del Escenario B.
* **Si no pulsas nada:** La moto se queda cargada al 80%, protegida para el día a día.

> 💡 La duración configurada (`4h` en este ejemplo) actúa como límite máximo de seguridad: si por lo que sea no se llegara exactamente al 80% (potencia de carga mal calibrada, etc.), a las **07:00** se apagaría igualmente.

