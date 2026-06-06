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

👉 **[Virtual EV Charging Card](https://github.com/tu_usuario/virtual-ev-charging-card)**

Esta tarjeta te permitirá deslizar el porcentaje de batería y la potencia, conmutar los modos de carga y ver animaciones de flujo energético en tiempo real directamente desde tu Dashboard con una sola línea de código:

```yaml
type: custom:virtual-ev-charging-card


📝 Ejemplo Práctico de Uso Diario
​Imagina que tienes una moto eléctrica con una batería de 13 kWh y cargas habitualmente en casa con un enchufe estándar a 1.4 kW.
​Escenario A: Carga Inteligente con el Sol (Proteger batería al 80%)
​Llegas al garaje tras usar la moto y ves que el marcador de la moto indica un 20% de batería. Enchufas el cargador.
​Abres Home Assistant y, en tu Virtual EV Charging Card, arrastras el deslizador de batería al 20%.
​El sistema calcula automáticamente las métricas iniciales:
​Energía restante al 80%: 8.86 kWh (60% de capacidad necesaria + pérdidas).
​Tiempo restante estimado: 6h 20m.
​Activas el interruptor Modo Automático Solar (el umbral está fijado en 3000W).
​A las 11:00 AM: Tus placas solares superan los 3000W. La estación se activa sola y recibes un aviso en Telegram.
​A la 1:30 PM: Pasa una nube densa y la producción baja a 1500W. El enchufe se apaga. El sistema guarda en memoria que ya se han inyectado 3.5 kWh.
​A las 2:00 PM: Vuelve el sol radiante (>3000W). El enchufe se enciende de nuevo. El sistema descuenta lo cargado y marca que ahora restan 5.36 kWh.
​Al completarse: En cuanto el contador del enchufe inteligente registra que han pasado los 8.86 kWh totales calculados inicialmente, la estación apaga el enchufe por completo, desarma el modo solar para el día siguiente y te avisa: ¡Carga al 80% completada con éxito!
​Escenario B: Carga Nocturna o Urgente (Llenar al 100%)
​Necesitas hacer un viaje largo mañana, así que necesitas la moto al máximo.
​Conectas la moto y simplemente activas el interruptor Forzar Carga desde Red.
​El cargador se enciende al instante ignorando el sol. Al pasar por el equivalente del 80%, recibes un Telegram de progreso informándote de que la carga continúa hacia el 100%.
​De madrugada, la batería se llena por completo. El BMS de la moto reduce el consumo drásticamente.
​Tras detectar que el cargador consume menos de 15W durante 5 minutos, la integración apaga el enchufe para que el cargador no sufra estrés, desactiva el botón de Red y te envía el aviso final a tu móvil.
