from homeassistant.components.switch import SwitchEntity
from .const import DOMAIN, CONF_ENCHUFE

async def async_setup_entry(hass, entry, async_add_entities):
    conf_enchufe = entry.data.get("enchufe_switch") or entry.data.get(CONF_ENCHUFE)
    
    async_add_entities([
        EVSwitch(entry, "modo_automatico_solar", "Carga Automática Solar", "mdi:solar-power"),
        EVSwitch(entry, "forzar_carga_red", "Forzar Carga desde Red", "mdi:transmission-tower"),
        # NUEVO: Control directo sobre el relé físico
        EVProxySwitch(entry, "interruptor_cargador", "Interruptor Cargador", "mdi:power-socket-eu", conf_enchufe)
    ])

class EVSwitch(SwitchEntity):
    def __init__(self, entry, id_name, display_name, icon):
        self.entity_id = f"switch.{DOMAIN}_{id_name}"
        self._attr_name = display_name
        self._attr_unique_id = f"{entry.entry_id}_{id_name}"
        self._attr_is_on = False
        self._attr_icon = icon

    async def async_turn_on(self, **kwargs):
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs):
        self._attr_is_on = False
        self.async_write_ha_state()

class EVProxySwitch(SwitchEntity):
    """Interruptor espejo: si lo tocas aquí, manda la orden directa al enchufe físico."""
    def __init__(self, entry, id_name, display_name, icon, conf_enchufe):
        self.entity_id = f"switch.{DOMAIN}_{id_name}"
        self._attr_name = display_name
        self._attr_unique_id = f"{entry.entry_id}_{id_name}"
        self._attr_icon = icon
        self._conf_enchufe = conf_enchufe

    @property
    def is_on(self):
        if not self._conf_enchufe: return False
        return self.hass.states.is_on(self._conf_enchufe)

    async def async_turn_on(self, **kwargs):
        if self._conf_enchufe:
            await self.hass.services.async_call("homeassistant", "turn_on", {"entity_id": self._conf_enchufe})
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs):
        if self._conf_enchufe:
            await self.hass.services.async_call("homeassistant", "turn_off", {"entity_id": self._conf_enchufe})
        self.async_write_ha_state()
