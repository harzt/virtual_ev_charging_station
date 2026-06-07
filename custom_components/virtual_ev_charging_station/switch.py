import logging
from homeassistant.components.switch import SwitchEntity
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities):
    """Configura los interruptores."""
    try:
        _LOGGER.info(f"[{DOMAIN}] Configurando switches...")
        async_add_entities([
            EVSwitch(entry, "modo_automatico_solar", "Carga Automática Solar", "mdi:solar-power"),
            EVSwitch(entry, "forzar_carga_red", "Forzar Carga desde Red", "mdi:transmission-tower")
        ])
        _LOGGER.debug(f"[{DOMAIN}] Switches configurados correctamente")
    except Exception as e:
        _LOGGER.error(f"[{DOMAIN}] Error configurando switches: {e}", exc_info=True)

class EVSwitch(SwitchEntity):
    """Entidad switch para controlar modos de carga."""
    
    def __init__(self, entry, id_name, display_name, icon):
        self.entity_id = f"switch.{DOMAIN}_{id_name}"
        self._attr_name = display_name
        self._attr_unique_id = f"{entry.entry_id}_{id_name}"
        self._attr_is_on = False
        self._attr_icon = icon
        self._id_name = id_name
        self._entry = entry

    @property
    def is_on(self):
        """Retorna el estado actual del switch."""
        return self._attr_is_on

    async def async_turn_on(self, **kwargs):
        """Enciende el switch."""
        try:
            _LOGGER.info(f"[{DOMAIN}] Encendiendo switch: {self._id_name}")
            self._attr_is_on = True
            self.async_write_ha_state()
            self.hass.bus.async_fire("virtual_ev_recalc")
            _LOGGER.debug(f"[{DOMAIN}] Switch {self._id_name} encendido y evento disparado")
        except Exception as e:
            _LOGGER.error(f"[{DOMAIN}] Error encendiendo switch {self._id_name}: {e}", exc_info=True)
            self._attr_is_on = False

    async def async_turn_off(self, **kwargs):
        """Apaga el switch."""
        try:
            _LOGGER.info(f"[{DOMAIN}] Apagando switch: {self._id_name}")
            self._attr_is_on = False
            self.async_write_ha_state()
            self.hass.bus.async_fire("virtual_ev_recalc")
            _LOGGER.debug(f"[{DOMAIN}] Switch {self._id_name} apagado y evento disparado")
        except Exception as e:
            _LOGGER.error(f"[{DOMAIN}] Error apagando switch {self._id_name}: {e}", exc_info=True)
            self._attr_is_on = True
