"""
Adds support for generic thermostat units.
For more details about this platform, please refer to the documentation at
https://home-assistant.io/components/climate.generic_thermostat/
"""
import asyncio
import logging

import voluptuous as vol

from homeassistant.const import (
    ATTR_ENTITY_ID, ATTR_TEMPERATURE, CONF_NAME, PRECISION_HALVES,
    PRECISION_TENTHS, PRECISION_WHOLE, SERVICE_TURN_OFF, SERVICE_TURN_ON,
    STATE_OFF, STATE_ON, STATE_UNKNOWN)
from homeassistant.core import DOMAIN as HA_DOMAIN, callback
from homeassistant.helpers import condition
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.event import (
    async_track_state_change, async_track_time_interval)
from homeassistant.helpers.restore_state import RestoreEntity

from homeassistant.components.climate import PLATFORM_SCHEMA, ClimateDevice
from homeassistant.components.climate.const import (
    ATTR_AWAY_MODE, ATTR_OPERATION_MODE, STATE_AUTO, STATE_COOL, STATE_HEAT,
    STATE_IDLE, SUPPORT_AWAY_MODE, SUPPORT_OPERATION_MODE,
    SUPPORT_TARGET_TEMPERATURE)

_LOGGER = logging.getLogger(__name__)

DEFAULT_TOLERANCE = 0.3
DEFAULT_NAME = 'CCL Generic Thermostat'

CONF_HEATER = 'heater'
CONF_SENSOR = 'target_sensor'
CONF_MIN_TEMP = 'min_temp'
CONF_MAX_TEMP = 'max_temp'
CONF_TARGET_TEMP = 'target_temp'
CONF_AC_MODE = 'ac_mode'
CONF_MIN_DUR = 'min_cycle_duration'
CONF_COLD_TOLERANCE = 'cold_tolerance'
CONF_HOT_TOLERANCE = 'hot_tolerance'
CONF_KEEP_ALIVE = 'keep_alive'
CONF_INITIAL_OPERATION_MODE = 'initial_operation_mode'
CONF_AWAY_TEMP = 'away_temp'
CONF_PRECISION = 'precision'
SUPPORT_FLAGS = (SUPPORT_TARGET_TEMPERATURE |
                 SUPPORT_OPERATION_MODE)

CONF_HEAT =  'heat'
CONF_REGULATION =  'regulation'
CONF_STATE =  'state'
CONF_REGULATION_DURATION = 'regulation_duration'
CONF_REGULATION_NB_DURATION = 'regulation_nb_duration'
CONF_REGULATION_DELTA = 'regulation_delta'
STATE_REGULATION = 'regulation'
STATE_STANDBY = 'standby'

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_HEATER): cv.entity_id,
    vol.Required(CONF_SENSOR): cv.entity_id,
    vol.Optional(CONF_AC_MODE): cv.boolean,
    vol.Optional(CONF_MAX_TEMP): vol.Coerce(float),
    vol.Optional(CONF_MIN_DUR): vol.All(cv.time_period, cv.positive_timedelta),
    vol.Optional(CONF_MIN_TEMP): vol.Coerce(float),
    vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
    vol.Optional(CONF_COLD_TOLERANCE, default=DEFAULT_TOLERANCE): vol.Coerce(
        float),
    vol.Optional(CONF_HOT_TOLERANCE, default=DEFAULT_TOLERANCE): vol.Coerce(
        float),
    vol.Optional(CONF_TARGET_TEMP): vol.Coerce(float),
    vol.Optional(CONF_KEEP_ALIVE): vol.All(
        cv.time_period, cv.positive_timedelta),
    vol.Optional(CONF_INITIAL_OPERATION_MODE):
        vol.In([STATE_AUTO, STATE_OFF]),
    vol.Optional(CONF_AWAY_TEMP): vol.Coerce(float),
    vol.Optional(CONF_PRECISION): vol.In(
        [PRECISION_TENTHS, PRECISION_HALVES, PRECISION_WHOLE]),

    vol.Optional(CONF_REGULATION_DURATION): vol.All(
        cv.time_period, cv.positive_timedelta),
    vol.Optional(CONF_REGULATION_NB_DURATION): vol.Coerce(int),
    vol.Optional(CONF_REGULATION_DELTA): vol.Coerce(float),
    vol.Optional(CONF_HEAT): cv.entity_id,
    vol.Optional(CONF_REGULATION): cv.entity_id,
    vol.Optional(CONF_STATE): cv.entity_id
})


async def async_setup_platform(hass, config, async_add_entities,
                               discovery_info=None):
    """Set up the generic thermostat platform."""
    name = config.get(CONF_NAME)
    heater_entity_id = config.get(CONF_HEATER)
    sensor_entity_id = config.get(CONF_SENSOR)
    min_temp = config.get(CONF_MIN_TEMP)
    max_temp = config.get(CONF_MAX_TEMP)
    target_temp = config.get(CONF_TARGET_TEMP)
    ac_mode = config.get(CONF_AC_MODE)
    min_cycle_duration = config.get(CONF_MIN_DUR)
    cold_tolerance = config.get(CONF_COLD_TOLERANCE)
    hot_tolerance = config.get(CONF_HOT_TOLERANCE)
    keep_alive = config.get(CONF_KEEP_ALIVE)
    initial_operation_mode = config.get(CONF_INITIAL_OPERATION_MODE)
    away_temp = config.get(CONF_AWAY_TEMP)
    precision = config.get(CONF_PRECISION)

    heat_entity_id = config.get(CONF_HEAT)
    regulation_entity_id = config.get(CONF_REGULATION)
    state_entity_id = config.get(CONF_STATE)
    regulation_duration = config.get(CONF_REGULATION_DURATION)
    regulation_nb_duration = config.get(CONF_REGULATION_NB_DURATION)
    regulation_delta = config.get(CONF_REGULATION_DELTA)

    async_add_entities([CCLGenericThermostat(
        hass, name, heater_entity_id, sensor_entity_id, min_temp, max_temp,
        target_temp, ac_mode, min_cycle_duration, cold_tolerance,
        hot_tolerance, keep_alive, initial_operation_mode, away_temp,
        precision,
        heat_entity_id, regulation_entity_id, state_entity_id,
        regulation_duration, regulation_nb_duration, regulation_delta
        )])


class CCLGenericThermostat(ClimateDevice, RestoreEntity):
    """Representation of a Generic Thermostat device."""

    def __init__(self, hass, name, heater_entity_id, sensor_entity_id,
                 min_temp, max_temp, target_temp, ac_mode, min_cycle_duration,
                 cold_tolerance, hot_tolerance, keep_alive,
                 initial_operation_mode, away_temp, precision,
                 heat_entity_id, regulation_entity_id, state_entity_id,
                 regulation_duration, regulation_nb_duration, regulation_delta
                 ):
        """Initialize the thermostat."""
        self.hass = hass
        self._name = name
        self.heater_entity_id = heater_entity_id
        self.ac_mode = ac_mode
        self.min_cycle_duration = min_cycle_duration
        self._cold_tolerance = cold_tolerance
        self._hot_tolerance = hot_tolerance
        self._keep_alive = keep_alive
        self._initial_operation_mode = initial_operation_mode
        self._saved_target_temp = target_temp if target_temp is not None \
            else away_temp
        self._temp_precision = precision
        if self.ac_mode:
            self._current_operation = STATE_COOL
            self._operation_list = [STATE_COOL, STATE_OFF]
        else:
            self._current_operation = STATE_HEAT
            self._operation_list = [STATE_HEAT, STATE_OFF]
        if initial_operation_mode == STATE_OFF:
            self._enabled = False
            self._current_operation = STATE_OFF
        else:
            self._enabled = True
        self._active = False
        self._cur_temp = None
        self._temp_lock = asyncio.Lock()
        self._min_temp = min_temp
        self._max_temp = max_temp
        self._target_temp = target_temp
        self._unit = hass.config.units.temperature_unit
        self._support_flags = SUPPORT_FLAGS
        if away_temp is not None:
            self._support_flags = SUPPORT_FLAGS | SUPPORT_AWAY_MODE
        self._away_temp = away_temp
        self._is_away = False

        async_track_state_change(
            hass, sensor_entity_id, self._async_sensor_changed)
        async_track_state_change(
            hass, heater_entity_id, self._async_switch_changed)

        if self._keep_alive:
            async_track_time_interval(
                hass, self._async_control_heating, self._keep_alive)

        sensor_state = hass.states.get(sensor_entity_id)
        if sensor_state and sensor_state.state != STATE_UNKNOWN:
            self._async_update_temp(sensor_state)

        self._heat_entity_id = heat_entity_id
        self._regulation_entity_id = regulation_entity_id
        self._state_entity_id = state_entity_id
        self._regulation_duration = regulation_duration
        self._regulation_nb_duration = regulation_nb_duration
        self._regulation_delta = regulation_delta
        self._nb_tick_regulation = 0

        if self._regulation_duration:
            async_track_time_interval(
                hass, self._async_regulation, self._regulation_duration)

        
    async def async_added_to_hass(self):
        """Run when entity about to be added."""
        await super().async_added_to_hass()
        # Check If we have an old state
        old_state = await self.async_get_last_state()
        if old_state is not None:
            # If we have no initial temperature, restore
            if self._target_temp is None:
                # If we have a previously saved temperature
                if old_state.attributes.get(ATTR_TEMPERATURE) is None:
                    if self.ac_mode:
                        self._target_temp = self.max_temp
                    else:
                        self._target_temp = self.min_temp
                    _LOGGER.warning("Undefined target temperature,"
                                    "falling back to %s", self._target_temp)
                else:
                    self._target_temp = float(
                        old_state.attributes[ATTR_TEMPERATURE])
            if old_state.attributes.get(ATTR_AWAY_MODE) is not None:
                self._is_away = str(
                    old_state.attributes[ATTR_AWAY_MODE]) == STATE_ON
            if (self._initial_operation_mode is None and
                    old_state.attributes[ATTR_OPERATION_MODE] is not None):
                self._current_operation = \
                    old_state.attributes[ATTR_OPERATION_MODE]
                self._enabled = self._current_operation != STATE_OFF

        else:
            # No previous state, try and restore defaults
            if self._target_temp is None:
                if self.ac_mode:
                    self._target_temp = self.max_temp
                else:
                    self._target_temp = self.min_temp
            _LOGGER.warning("No previously saved temperature, setting to %s",
                            self._target_temp)

    @property
    def state(self):
        """Return the current state."""
        if self._is_device_active:
            return self.current_operation
        if self._enabled:
            return STATE_IDLE
        return STATE_OFF

    @property
    def should_poll(self):
        """Return the polling state."""
        return False

    @property
    def name(self):
        """Return the name of the thermostat."""
        return self._name
    
    @property
    def precision(self):
        """Return the precision of the system."""
        if self._temp_precision is not None:
            return self._temp_precision
        return super().precision

    @property
    def temperature_unit(self):
        """Return the unit of measurement."""
        return self._unit

    @property
    def current_temperature(self):
        """Return the sensor temperature."""
        return self._cur_temp

    @property
    def current_operation(self):
        """Return current operation."""
        return self._current_operation

    @property
    def target_temperature(self):
        """Return the temperature we try to reach."""
        return self._target_temp

    @property
    def operation_list(self):
        """List of available operation modes."""
        return self._operation_list

    async def async_set_operation_mode(self, operation_mode):
        """Set operation mode."""
        if operation_mode == STATE_HEAT:
            self._current_operation = STATE_HEAT
            self._enabled = True
            await self._async_control_heating(force=True)
        elif operation_mode == STATE_COOL:
            self._current_operation = STATE_COOL
            self._enabled = True
            await self._async_control_heating(force=True)
        elif operation_mode == STATE_OFF:
            self._current_operation = STATE_OFF
            self._enabled = False
            if self._is_device_active:
                await self._async_heater_turn_off()
        else:
            _LOGGER.error("Unrecognized operation mode: %s", operation_mode)
            return
        # Ensure we update the current operation after changing the mode
        self.schedule_update_ha_state()

    async def async_turn_on(self):
        """Turn thermostat on."""
        await self.async_set_operation_mode(self.operation_list[0])

    async def async_turn_off(self):
        """Turn thermostat off."""
        await self.async_set_operation_mode(STATE_OFF)

    async def async_set_temperature(self, **kwargs):
        """Set new target temperature."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return
        self._target_temp = temperature
        await self._async_control_heating(force=True)
        await self.async_update_ha_state()

    @property
    def min_temp(self):
        """Return the minimum temperature."""
        if self._min_temp:
            return self._min_temp

        # get default temp from super class
        return super().min_temp

    @property
    def max_temp(self):
        """Return the maximum temperature."""
        if self._max_temp:
            return self._max_temp

        # Get default temp from super class
        return super().max_temp

    async def _async_sensor_changed(self, entity_id, old_state, new_state):
        """Handle temperature changes."""
        if new_state is None:
            return

        self._async_update_temp(new_state)
        await self._async_control_heating()
        await self.async_update_ha_state()

    @callback
    def _async_switch_changed(self, entity_id, old_state, new_state):
        """Handle heater switch state changes."""
        if new_state is None:
            return
        self.async_schedule_update_ha_state()

    @callback
    def _async_update_temp(self, state):
        """Update thermostat with latest state from sensor."""
        try:
            self._cur_temp = float(state.state)
        except ValueError as ex:
            _LOGGER.error("Unable to update from sensor: %s", ex)

    async def _async_control_heating(self, time=None, force=False):
        """Check if we need to turn heating on or off."""
        _LOGGER.debug("Check if we need to turn heating on or off")
        async with self._temp_lock:
            if not self._active and None not in (self._cur_temp,
                                                 self._target_temp):
                self._active = True
                _LOGGER.info("Obtained current and target temperature. "
                             "Generic thermostat active. %s, %s",
                             self._cur_temp, self._target_temp)

            if not self._active or not self._enabled:
                return

            next_state = self._current_operation
            is_heating = self._is_device_active
            if is_heating:
                too_hot = self._cur_temp - self._target_temp >= \
                    self._hot_tolerance
                if too_hot:
                    next_state = STATE_STANDBY
                else:
                    _LOGGER.debug("Evaluate regulation mode for heater %s",
                                    self.heater_entity_id)
                    regulation_mode = self._cur_temp >= \
                        self._target_temp - self._regulation_delta
                    if regulation_mode:
                        next_state = STATE_REGULATION
                    else:
                        next_state = STATE_HEAT
            else:
                too_cold = self._target_temp - self._cur_temp >= \
                    self._cold_tolerance
                if too_cold:
                    next_state = STATE_HEAT
                else:
                    next_state = STATE_STANDBY
            _LOGGER.debug("Next state for heater %s : %s (force: %s, time: %s)", self.heater_entity_id, next_state, force, time)

            if not force and time is None:
                # If the `force` argument is True, we
                # ignore `min_cycle_duration`.
                # If the `time` argument is not none, we were invoked for
                # keep-alive purposes, and `min_cycle_duration` is irrelevant.
                if self.min_cycle_duration:
                    if self._is_device_active:
                        current_state = STATE_ON
                    else:
                        current_state = STATE_OFF
                    if next_state == STATE_STANDBY:
                        next_current_state = STATE_OFF
                    else:
                        next_current_state = STATE_ON
                    if current_state != next_current_state:
                        _LOGGER.debug("State : %s since %s", self.hass.states.get(self._heat_entity_id).state, self.hass.states.get(self._heat_entity_id).last_changed)
                        long_enough = condition.state(
                            self.hass, self._heat_entity_id, current_state,
                            self.min_cycle_duration)
                        if not long_enough:
                            _LOGGER.debug("Min cycle duration not reach for heater %s", self._heat_entity_id)
                            return

            await self._async_set_heating_mode(next_state, time)

    async def _async_regulation(self, time=None):
        """Call at constant intervals for regulation purposes."""
        _LOGGER.debug("Check if in regulation for heater %s",
                                    self.heater_entity_id)
        if self._is_in_regulation:
            _LOGGER.debug("Check regulation for heater %s",
                                    self.heater_entity_id)
            self._nb_tick_regulation = self._nb_tick_regulation + 1
            if self._nb_tick_regulation == self._regulation_nb_duration:
                _LOGGER.debug("Regulation tick for heater %s",
                                    self.heater_entity_id)
                self._nb_tick_regulation = 0
                await self._async_heater_turn_on()
            else:
                _LOGGER.debug("Regulation untick for heater %s",
                                    self.heater_entity_id)
                await self._async_heater_turn_off()

    async def _async_set_heating_mode(self, heating_mode, time):
        """Set heating mode."""
        _LOGGER.debug("Set heating mode to %s", heating_mode)
        #if self._is_device_active:
        if heating_mode == STATE_HEAT:
            _LOGGER.info("Turning on heater %s", self._heat_entity_id)
            await self._async_heat_turn_on()
            await self._async_regulation_turn_off()
            await self._async_state_select(heating_mode)
            await self._async_heater_turn_on()
        elif heating_mode == STATE_REGULATION:
            _LOGGER.info("Turning heater %s on regulation", self._heat_entity_id)
            await self._async_heat_turn_on()
            await self._async_regulation_turn_on()
            await self._async_state_select(heating_mode)
            await self._async_heater_turn_on()
        elif heating_mode == STATE_STANDBY:
            _LOGGER.info("Turning heater %s on standby",
                                self._heat_entity_id)
            await self._async_heat_turn_off()
            await self._async_regulation_turn_off()
            await self._async_state_select(heating_mode)
            await self._async_heater_turn_off()
        else:
            _LOGGER.error("Unrecognized heating mode: %s", heating_mode)
            return

    @property
    def _is_device_active(self):
        """If the toggleable device is currently active."""
        #return self.hass.states.is_state(self.heater_entity_id, STATE_ON)
        return self.hass.states.is_state(self._heat_entity_id, STATE_ON)
    
    @property
    def _is_in_regulation(self):
        """If the toggleable device is currently active."""
        #return self.hass.states.is_state(self.heater_entity_id, STATE_ON)
        return self.hass.states.is_state(self._regulation_entity_id, STATE_ON)
            
    @property
    def supported_features(self):
        """Return the list of supported features."""
        return self._support_flags

    async def _async_heater_turn_on(self):
        """Turn heater toggleable device on."""
        data = {ATTR_ENTITY_ID: self.heater_entity_id}
        await self.hass.services.async_call(HA_DOMAIN, SERVICE_TURN_ON, data)
    
    async def _async_heater_turn_off(self):
        """Turn heater toggleable device off."""
        data = {ATTR_ENTITY_ID: self.heater_entity_id}
        await self.hass.services.async_call(HA_DOMAIN, SERVICE_TURN_OFF, data)

    async def _async_heat_turn_on(self):
        """Turn heat toggleable device off."""
        data = {ATTR_ENTITY_ID: self._heat_entity_id}
        await self.hass.services.async_call(HA_DOMAIN, SERVICE_TURN_ON, data)

    async def _async_heat_turn_off(self):
        """Turn heat toggleable device off."""
        data = {ATTR_ENTITY_ID: self._heat_entity_id}
        await self.hass.services.async_call(HA_DOMAIN, SERVICE_TURN_OFF, data)
    
    async def _async_regulation_turn_on(self):
        """Turn heat toggleable device on."""
        data = {ATTR_ENTITY_ID: self._regulation_entity_id}
        await self.hass.services.async_call(HA_DOMAIN, SERVICE_TURN_ON, data)

    async def _async_regulation_turn_off(self):
        """Turn heat toggleable device off."""
        data = {ATTR_ENTITY_ID: self._regulation_entity_id}
        await self.hass.services.async_call(HA_DOMAIN, SERVICE_TURN_OFF, data)
    
    async def _async_state_select(self, state):
        """Switch state"""
        data = {ATTR_ENTITY_ID: self._state_entity_id, ATTR_OPTION: state}
        await self.hass.services.async_call('input_select', SERVICE_SELECT_OPTION, data)

    @property
    def is_away_mode_on(self):
        """Return true if away mode is on."""
        return self._is_away

    async def async_turn_away_mode_on(self):
        """Turn away mode on by setting it on away hold indefinitely."""
        if self._is_away:
            return
        self._is_away = True
        self._saved_target_temp = self._target_temp
        self._target_temp = self._away_temp
        await self._async_control_heating(force=True)
        await self.async_update_ha_state()

    async def async_turn_away_mode_off(self):
        """Turn away off."""
        if not self._is_away:
            return
        self._is_away = False
        self._target_temp = self._saved_target_temp
        await self._async_control_heating(force=True)
        await self.async_update_ha_state()