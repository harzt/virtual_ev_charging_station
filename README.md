# Virtual EV Charging Station 🚗⚡

**Virtual EV Charging Station** es una integración personalizada para Home Assistant que convierte cualquier enchufe inteligente con medición de consumo en un cargador inteligente virtual para tu vehículo eléctrico o moto. 

Está diseñada especialmente para vehículos sin conectividad nativa (API), permitiendo proteger la vida útil de su batería mediante paradas automáticas al **80%** calculadas por software, optimización de excedentes fotovoltaicos y carga forzada desde la red eléctrica.

---

## 🚀 Características principales

* **Cálculo dinámico por energía (kWh):** Olvídate del tiempo fijo. La integración mide los kWh reales extraídos del enchufe para clavar la parada al 80%.
* **Cuenta atrás en tiempo real:** Sensores dinámicos de energía restante y tiempo estimado que decrecen minuto a minuto durante la carga.
* **Gestión de Excedentes Solares:** Arranca y pausa la carga automáticamente según la producción de tus placas solares y el umbral ajustable que elijas.
* **Memoria inteligente contra nubes:** Si una nube apaga el cargador, el sistema retiene el objetivo original y reanuda el conteo exacto al volver el sol.
* **Modo Forzar Red al 100% (BMS):** Carga continua sin importar el sol. Al llegar al 100%, detecta la caída de consumo del Sistema de Gestión de Batería (BMS) de tu vehículo y corta el enchufe por seguridad.

---

## ⚙️ ¿Cómo funciona internamente?

La integración opera de forma completamente autónoma en el núcleo de Home Assistant bajo la siguiente lógica:

1. **Planificación:** Al ajustar el **Porcentaje Actual** de tu vehículo y la **Potencia de Carga**, el sistema calcula instantáneamente cuántos kWh netos faltan para el objetivo aplicando un factor de eficiencia del **88%** (pérdidas térmicas del cargador).
2. **Activación de Carga:** En cuanto el enchufe se enciende (vía Sol o vía Red), la integración lee el valor absoluto actual de tu contador de energía y fija de forma persistente la **Energía de Corte**.
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

> 💡 **Parámetros de partida para los ejemplos:** Vehículo con batería de **13 kWh** cargando en un enchufe inteligente limitado a **1.4 kW** (eficiencia estimada del 88%).

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

### 🔌 Escenario B: Carga de Emergencia o Nocturna (Llenar al 100%)

Ideal para cuando necesitas exprimir la autonomía máxima del vehículo porque tienes previsto realizar un viaje largo al día siguiente.

* **09:00 PM | Activación:** Conectas la moto al garaje y enciendes el interruptor **Forzar Carga desde Red**.
* **09:01 PM | Arranque Inmediato:** El cargador se activa en el acto ignorando por completo que ya es de noche y no hay sol:
    > ⚡ **Carga de Moto Iniciada:** Cargador forzado desde la Red. Objetivo final: 100% de batería.
* **03:20 AM | Hito del 80%:** El sistema detecta que han pasado los kWh equivalentes al 80%, pero sabe que el interruptor de red está encendido, por lo que **no corta la corriente** y te envía un aviso de progreso:
    > ⏳ **Moto al 80% (Modo Red):** Se ha alcanzado el 80% de carga estimada. El proceso continúa adelante hasta llenar el 100% de la batería.
* **04:45 AM | Actuación del BMS:** La batería llega a su límite real del 100%. El sistema de gestión interna de la moto (BMS) reduce drásticamente la potencia para equilibrar las celdas.
* **04:50 AM | Apagado por Seguridad:** Tras registrar que la potencia de carga lleva **5 minutos seguidos por debajo de 15W**, la integración asume que el proceso ha terminado. Apaga el enchufe para proteger el transformador, desactiva el botón de Red y te envía el reporte final:
    > 🔋 **Carga al 100% Completada:** El enchufe se ha apagado tras detectar un consumo mínimo (Batería llena o moto desconectada).
 
