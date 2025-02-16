"""Platform for light integration"""
from __future__ import annotations
from collections import OrderedDict

import json
import logging, logging.handlers
import sys, os
import voluptuous as vol
import asyncio
from homeassistant.components import mqtt

from homeassistant.components.light import (  # ATTR_EFFECT,; ATTR_FLASH,; ATTR_WHITE_VALUE,; PLATFORM_SCHEMA,; SUPPORT_EFFECT,; SUPPORT_FLASH,; SUPPORT_WHITE_VALUE,; ATTR_SUPPORTED_COLOR_MODES,
    ATTR_BRIGHTNESS,
    ATTR_COLOR_MODE,
    ATTR_COLOR_TEMP,
    ATTR_EFFECT,
    ATTR_EFFECT_LIST,
    ATTR_HS_COLOR,
    ATTR_MAX_MIREDS,
    ATTR_MIN_MIREDS,
    ATTR_RGB_COLOR,
    ATTR_TRANSITION,
    ENTITY_ID_FORMAT,
    SUPPORT_BRIGHTNESS,
    SUPPORT_COLOR,
    SUPPORT_COLOR_TEMP,
    SUPPORT_TRANSITION,
    SUPPORT_EFFECT,
    LightEntity,
    PLATFORM_SCHEMA,
    ColorMode
)
from homeassistant.const import (  # ATTR_SUPPORTED_FEATURES,; CONF_ENTITY_ID,; CONF_NAME,; CONF_OFFSET,; CONF_UNIQUE_ID,; EVENT_HOMEASSISTANT_START,; STATE_ON,; STATE_UNAVAILABLE,
    ATTR_ENTITY_ID,
    #ATTR_UNIQUE_ID
)

# from enum import Enum
import homeassistant.helpers.config_validation as cv
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import event
from homeassistant.helpers.entity import generate_entity_id
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from .right_light import RightLight

_LOGGER = logging.getLogger(__name__)

# Uncomment the next lines to enable remote logging of events
# _LOGGER.setLevel(logging.ERROR)
# lh = logging.handlers.SysLogHandler(address=("192.168.1.7", 514))
# _LOGGER.addHandler(lh)

CONF_NAME = "name"
CONF_UNIQUE_ID= "unique_id"
CONF_ENTITIES = "entities"
CONF_SWITCHES = "switch"
CONF_MOTION_SENSORS = "motion_sensors"
CONF_MOTION_SENSORS_FULL_BRIGHTNESS = "full_brightness_motion_sensors"
CONF_MOTION_DISABLE_ENTITIES = "motion_disable_entities"
CONF_MOTION_SENSOR_TRANSITION = "motion_sensor_transition"
CONF_MOTION_SENSOR_TIMEOUT = "motion_sensor_timeout"
CONF_HAS_BRIGHTNESS_THRESHOLD = "has_brightness_threshold"
CONF_MOTION_SENSOR_BRIGHTNESS = "motion_sensor_brightness"
CONF_OTHER_LIGHT_TRACKERS = "other_light_trackers"
CONF_TRACK_OTHER_LIGHT_OFF_EVENTS = "track_other_light_off_events"
CONF_ENTITIES_BELOW_THRESHOLD = "entities_below_threshold"
CONF_ENTITIES_ABOVE_THRESHOLD = "entities_above_threshold"
CONF_BRIGHTNESS_MULTIPLIER = "brightness_multiplier"
CONF_BUTTON_MAP = "button_map"
CONF_HAS_BUTTON_MAP = "has_button_map"

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        #vol.Required(CONF_PLATFORM): "NewZoneLight",
        vol.Required(CONF_NAME): cv.string,
        vol.Optional(CONF_UNIQUE_ID): cv.string,
        vol.Optional(CONF_ENTITIES): cv.entity_ids,
        vol.Optional(CONF_ENTITIES_BELOW_THRESHOLD): cv.entity_ids,
        vol.Optional(CONF_ENTITIES_ABOVE_THRESHOLD): cv.entity_ids,
        vol.Optional(CONF_SWITCHES): cv.string,
        vol.Optional(CONF_MOTION_SENSORS): cv.ensure_list,
        vol.Optional(CONF_MOTION_SENSORS_FULL_BRIGHTNESS): cv.ensure_list,
        vol.Optional(CONF_MOTION_DISABLE_ENTITIES): cv.entity_ids,
        vol.Optional(CONF_MOTION_SENSOR_TRANSITION): cv.positive_float,
        vol.Optional(CONF_MOTION_SENSOR_TIMEOUT): cv:positive_int,
        vol.Optional(CONF_HAS_BRIGHTNESS_THRESHOLD): cv.boolean,
        vol.Optional(CONF_MOTION_SENSOR_BRIGHTNESS): cv.positive_int,
        vol.Optional(CONF_OTHER_LIGHT_TRACKERS): cv.ensure_list,
        vol.Optional(CONF_TRACK_OTHER_LIGHT_OFF_EVENTS): cv.boolean,
        vol.Optional(CONF_BRIGHTNESS_MULTIPLIER): cv.ensure_list,
        vol.Optional(CONF_HAS_BUTTON_MAP): cv.boolean,
    }
)

def setup_platform(hass: HomeAssistant, config: ConfigType, async_add_entities: AddEntitiesCallback, discovery_info: DiscoveryInfoType | None = None) -> None:
    """Set up the New Zone Light configuration"""
    nzl = NewZoneLight(config.get(CONF_NAME))

    if config.get(CONF_ENTITIES):
        temp_dict = OrderedDict()
        for ent in config.get(CONF_ENTITIES):
            temp_dict[ent] = None
        nzl.entities = temp_dict

    nzl.switch = config.get(CONF_SWITCHES)

    if config.get(CONF_ENTITIES_BELOW_THRESHOLD):
        for ent in config.get(CONF_ENTITIES_BELOW_THRESHOLD):
            if not ent in nzl.entities:
                nzl.entities[ent] = None
            _LOGGER.debug(f"Adding {ent} below threshold")
            nzl.entities_below_threshold.append(ent)

    if config.get(CONF_ENTITIES_ABOVE_THRESHOLD):
        for ent in config.get(CONF_ENTITIES_ABOVE_THRESHOLD):
            if not ent in nzl.entities:
                nzl.entities[ent] = None
            _LOGGER.debug(f"Adding {ent} above threshold")
            nzl.entities_above_threshold.append(ent)

    _LOGGER.debug(f"All entities: {nzl.entities}")

    nzl.has_brightness_threshold = config.get(CONF_HAS_BRIGHTNESS_THRESHOLD)
    if config.get(CONF_MOTION_SENSORS):
        nzl.motion_sensors = config.get(CONF_MOTION_SENSORS)
    if config.get(CONF_MOTION_SENSORS_FULL_BRIGHTNESS):
        nzl.full_brightness_motion_sensors = config.get(CONF_MOTION_SENSORS_FULL_BRIGHTNESS)
    if config.get(CONF_MOTION_DISABLE_ENTITIES):
        nzl.motion_disable_entities = config.get(CONF_MOTION_DISABLE_ENTITIES)
    if config.get(CONF_MOTION_SENSOR_BRIGHTNESS):
        nzl.motion_sensor_brightness = config.get(CONF_MOTION_SENSOR_BRIGHTNESS)
    if config.get(CONF_OTHER_LIGHT_TRACKERS):
        temp_dict = OrderedDict()
        for entry in config.get(CONF_OTHER_LIGHT_TRACKERS):
            for ent, br in entry.items():
                temp_dict[ent] = br
        nzl.other_light_trackers = temp_dict

        if config.get(CONF_TRACK_OTHER_LIGHT_OFF_EVENTS):
            nzl.track_other_light_off_events = config.get(CONF_TRACK_OTHER_LIGHT_OFF_EVENTS)
    if config.get(CONF_MOTION_SENSOR_TRANSITION):
        nzl.motion_sensor_transition = config.get(CONF_MOTION_SENSOR_TRANSITION)
    if config.get(CONF_MOTION_SENSOR_TIMEOUT):
        nzl.motion_sensor_timeout = config.get(CONF_MOTION_SENSOR_TIMEOUT)

    if config.get(CONF_BRIGHTNESS_MULTIPLIER):
        temp_dict = OrderedDict()
        for entry in config.get(CONF_BRIGHTNESS_MULTIPLIER):
            for ent,br in entry.items():
                temp_dict[ent] = br
        nzl.brightness_multiplier = temp_dict

    nzl.has_button_map = config.get(CONF_HAS_BUTTON_MAP)

    async_add_entities([nzl])

    async def async_update(call: ServiceCall | None = None) -> None:
        """Update lights"""
        await nzl.async_update()

    #service_name = f"{name} update"
    #hass.services.async_register(LIGHT_DOMAIN, service_name, async_update)

class NewZoneLight(LightEntity):
    """New Light Super Class"""

    def __init__(self, name, domain="new_zone_light", debug=False, debug_rl=False) -> None:
        """Initialize NewLight Super Class."""

        if debug:
            _LOGGER.setLevel(logging.DEBUG)

        self.entities = OrderedDict()
        """Dictionary of entities.  Each will be a rightlight object and be addressable from the json buttonmap.  The first
        added entity will be the default entity for this light.  The second entity will be used for above brightness threshold."""

        self.entities_below_threshold = []
        """List of entities to enable when brightness is below the threshold.  If empty, will use first entity."""

        self.entities_above_threshold = []
        """List of entities to enable when brightness is above the threshold.  If empty, will use second entity."""

        self.brightness_multiplier = {}
        """Dictionary of entity keys to brightness multipliers"""

        # self.has_switch = False
        # """Does this light have an associated switch?  Override to set to true if needed"""

        self.switch = None
        """MQTT topic to monitor for switch activity.  Typically '<room> Switch' """

        self.motion_sensors = []
        """A list of motion sensors that can turn this light on and off"""

        self.full_brightness_motion_sensors = []
        """A list of motion sensors that can turn this light on and off, but to full brightness"""

        self.has_brightness_threshold = False
        """Does this light use a brightness threshold switch?  Override to set to true if needed"""

        self.brightness_threshold = 128
        """Brightness threshold above which to also turn on second light entity"""

        # self.harmony_entity = None
        # """Entity name of harmony hub if one exists"""

        self.motion_disable_entities = []
        """List of entities for which to disable motion sensing if they're on"""

        self.motion_disable_trackers = {}
        """Dictionary of current states for motion disable entities"""

        self.brightness_step = 43
        """Step to increment/decrement brightness when using a switch"""

        self.motion_sensor_brightness = 192
        """Brightness of this light when a motion sensor turns it on"""

        self.switch_transition = 0.2
        """Default transition when a switch is triggered"""

        self.motion_sensor_transition = 0.4
        """Default transition when a motion sensor is triggered"""

        self.motion_sensor_timeout = 15
        """Default number of seconds after motion sensor off event before triggering off"""

        self.default_transition = 0.1
        """Default transition when no source is known"""

        self.other_light_trackers = {}
        """Dictionary of entity=brightness values that turn this light on to brightness when entity turns on"""

        self.track_other_light_off_events = False
        """When set to true, will also turn off this light when all other lights being tracked are off"""

        self.turn_off_other_lights = False
        """Immediately turn back off any tracked light when an on event is received (for template lights as buttons)"""

        self._name = name
        """Name of this object"""

        self._brightness = 0
        """Light's current brightness"""
        self._brightnessBT = 0
        """Light's current below-threhold brightness (i.e. first entity brightness)"""
        self._brightnessAT = 0
        """Light's current above-threhold brightness (i.e. second entity brightness)"""
        self._brightness_override = 0
        """Allow brightness above 255 (for going brighter than RightLight default)"""
        self._hs_color: Optional[Tuple[float, float]] = None
        """Light's current color in hs"""
        self._color_temp: Optional[int] = None
        """Light's current color in Kelvin"""
        self._rgb_color: Optional[Tuple[int, int, int]] = None
        """Light's current color in RGB"""
        self._min_mireds: int = 154
        """Light's minimum supported mireds"""
        self._max_mireds: int = 500
        """Light's maximum supported mireds"""
        self._mode = "Off"
        """Light's current mode"""
        self._is_on = False
        """Boolean to show if light is on"""
        self._available = True
        """Boolean to show if light is available (always true)"""
        self._occupancies = {}
        """Array of booleans for tracking individual motion sensor states"""
        self._occupancy = False
        """Single attribute for tracking overall occupancy state"""
        self._full_brightness_occupancies = {}
        """Array of booleans for tracking individual full-brightness motion sensor states"""
        self._full_brightness_occupancy = False
        """Single attribute for tracking overall full-brightness occupancy state"""
        self._entity_id = generate_entity_id(ENTITY_ID_FORMAT, self.name, [])
        """Generates a unique entity ID based on instance's name"""
        # self._white_value: Optional[int] = None
        self._effect_list: Optional[List[str]] = None
        """A list of supported effects"""
        #self._curr_effect = "Normal"
        self._curr_effect = "Off"
        """Store the current effect being used"""
        self._button_map_file = f"custom_components/{domain}/{self.name}_button_map.json"
        """Name of the optional JSON button map file"""
        self._button_map_timestamp = 0
        """Store timestamp of previously loaded button map file"""
        self._button_map_data = {}
        """Data loaded from optional JSON button map script"""
        # self._effect: Optional[str] = None
        self._supported_features: int = 0
        """Supported features of this light.  OR togther SUPPORT_BRIGHTNESS, SUPPORT_COLOR_TEMP, SUPPORT_COLOR, SUPPORT_TRANSITION"""
        self._supported_features |= SUPPORT_BRIGHTNESS
        self._supported_features |= SUPPORT_COLOR_TEMP
        self._supported_features |= SUPPORT_COLOR
        self._supported_features |= SUPPORT_TRANSITION
        self._supported_features |= SUPPORT_EFFECT
        # self._supported_features |= SUPPORT_WHITE_VALUE

        self._buttonCounts = {
            "on-press": 0,
            "on-hold": 0,
            "up-press": 0,
            "up-hold": 0,
            "down-press": 0,
            "down-hold": 0,
            "off-press": 0,
            "off-hold": 0,
            "on_press": 0,
            "on_hold": 0,
            "up_press": 0,
            "up_hold": 0,
            "down_press": 0,
            "down_hold": 0,
            "off_press": 0,
            "off_hold": 0,
        }
        """Stores current button presses for handling JSON buttonmap lists"""

        self._switched_on = False
        """Boolean showing whether the light was turned on by a switch/GUI"""

        # self._harmony_on = False
        # """Track state of associated harmony hub"""

        self._debug = debug
        """Boolean to enable debug mode"""

        self._debug_rl = debug_rl
        """Boolean to enable RightLight debug mode"""

        self._others = {}
        """Dictionary of states of other lights being tracked"""

        if self._debug:
            _LOGGER.info(f"{self.name} Light initialized")

    async def async_added_to_hass(self) -> None:
        """Initialize light objects"""

        # Start with all motion sensor states as off
        for ms in self.motion_sensors:
            self._occupancies[ms] = False
        for ms in self.full_brightness_motion_sensors:
            self._full_brightness_occupancies[ms] = False

        # Dictionary to track other light states
        for ent in self.other_light_trackers:
            self._others[ent] = False

        # Instantiate per-entity rightlight objects
        for entname in self.entities.keys():
            self.entities[entname] = RightLight(entname, self.hass, self._debug_rl)

            # Add RightLight color mode to effects list
            #self._effect_list = ["Normal"] + self.entities[entname].getColorModes()
            self._effect_list = self.entities[entname].getColorModes()

        # Subscribe to switch events
        if self.switch != None:
            if ":" in self.switch:
                # ZHA type switch
                self.hass.bus.async_listen("zha_event", self.switch_message_received)
            else:
                # Zigbee2mqtt type switch
                switch_action = f"zigbee2mqtt/{self.switch}/action"
                await mqtt.async_subscribe(self.hass, switch_action, self.switch_message_received)

        # Subscribe to motion sensor events
        for ms in self.motion_sensors + self.full_brightness_motion_sensors:
            if "binary_sensor" in ms:
                event.async_track_state_change_event(
                    self.hass, ms, self.motion_sensor_message_received_zha
                )
            else:
                action = f"zigbee2mqtt/{ms}"
                await mqtt.async_subscribe(self.hass, action, self.motion_sensor_message_received)

        # if self.has_motion_sensor:
        #    await self.hass.components.mqtt.async_subscribe(
        #        self.motion_sensor_action, self.motion_sensor_message_received
        #    )

        ## Subscribe to harmony events
        # if self.harmony_entity != None:
        #    event.async_track_state_change_event(
        #        self.hass, self.harmony_entity, self.harmony_update
        #    )

        # Subscribe to motion_disable_entities events
        for ent in self.motion_disable_entities:
            event.async_track_state_change_event(
                self.hass, ent, self.motion_disable_entity_update
            )

        # Subscribe to other entity events
        for ent in self.other_light_trackers.keys():
            event.async_track_state_change_event(
                self.hass, ent, self.other_entity_update
            )

        self.async_schedule_update_ha_state(force_refresh=True)
    
    @property
    def should_poll(self):
        """Allows for color updates to be polled"""
        return True

    @property
    def name(self) -> str:
        """Return the display name of this light."""
        return self._name

    @property
    def is_on(self) -> bool | None:
        """Return true if light is on."""
        return self._is_on

    @property
    def device_info(self):
        prop = {
            "identifiers": {
                # Serial numbers are unique identifiers within a specific domain
                (self.name, self.unique_id)
            },
            "name": self.name,
            "manufacturer": "Aaron",
        }
        return prop

    @property
    def unique_id(self):
        """Return the unique id of the light."""
        return self._entity_id

    @property
    def available(self) -> bool:
        """Return whether the light group is available."""
        return self._available

    @property
    def brightness(self) -> Optional[int]:
        """Return the brightness of this light between 0..255."""
        return self._brightness

    @property
    def hs_color(self) -> Optional[Tuple[float, float]]:
        """Return the hue and saturation color value [float, float]."""
        return self._hs_color

    @property
    def color_temp(self) -> Optional[int]:
        """Return the CT color value in mireds."""
        return self._color_temp

    @property
    def min_mireds(self) -> int:
        """Return the coldest color_temp that this light group supports."""
        return self._min_mireds

    @property
    def max_mireds(self) -> int:
        """Return the warmest color_temp that this light group supports."""
        return self._max_mireds

    @property
    def rgb_color(self) -> tuple[int, int, int] | None:
        """Return the rgb color value [int, int, int]."""
        return self._rgb_color

    @property
    def supported_features(self) -> int:
        """Flag supported features."""
        return self._supported_features

    @property
    def supported_color_modes(self) -> set[ColorMode] | set[str] | None:
        """Reports the supported color modes as required by HA"""
        return set([ColorMode.COLOR_TEMP, ColorMode.RGB])

    @property
    def color_mode(self) -> ColorMode:
        return ColorMode.RGB

    @property
    def effect(self):
        return self._curr_effect
        # return "Normal"

    @property
    def effect_list(self) -> list[str] | None:
        """Return the RightLight modes are effect options"""
        return self._effect_list

    async def async_turn_on(self, **kwargs) -> None:
        """Instruct the light to turn on."""
        if self._debug:
            _LOGGER.debug(f"{self.name} LIGHT ASYNC_TURN_ON: {kwargs}")

        if "brightness" in kwargs:
            self._brightness = kwargs["brightness"]
        elif self._brightness == 0:
            self._brightness = 255

        if self.has_brightness_threshold:
            if self._brightness > self.brightness_threshold:
                self._brightnessBT = 255
                self._brightnessAT = (
                    255
                    * (self._brightness - self.brightness_threshold)
                    / (255 - self.brightness_threshold)
                )
            else:
                self._brightnessBT = (
                    255 * (self._brightness) / (self.brightness_threshold)
                )
                self._brightnessAT = 0
            if self._debug:
                _LOGGER.debug(
                    f"{self.name} LIGHT ASYNC_TURN_ON: BT: {self._brightnessBT}, AT: {self._brightnessAT}"
                )
                _LOGGER.debug(
                    f"{self.name} LIGHT ASYNC_TURN_ON: Entities: {self.entities.keys()}"
                )

        # Assume switched on for anything other than motion sensor sources
        if "source" in kwargs and kwargs["source"] == "MotionSensor":
            pass
        else:
            self._switched_on = True

        #        if "source" in kwargs and kwargs["source"] == "Switch":
        #            # Assume RightLight mode for all switch presses
        #            rl = True
        #        elif self._is_on == False:
        #            # If light is off, default to RightLight mode (can be overriden with color/colortemp attributes)
        #            rl = True
        #        else:
        #            rl = False
        # Always assume RightLight is enabled.  Will override based on ATTR_* inputs
        rl = True

        self._is_on = True
        self._mode = "On"

        # Select correct transition unless overridden by kwargs
        if "transition" in kwargs:
            data = {
                ATTR_ENTITY_ID: list(self.entities.keys())[0],
                "transition": kwargs["transition"],
            }
        else:
            if "source" in kwargs:
                if kwargs["source"] == "Switch":
                    data = {
                        ATTR_ENTITY_ID: list(self.entities.keys())[0],
                        "transition": self.switch_transition,
                    }
                elif kwargs["source"] == "MotionSensor":
                    data = {
                        ATTR_ENTITY_ID: list(self.entities.keys())[0],
                        "transition": self.motion_sensor_transition,
                    }
                else:
                    data = {
                        ATTR_ENTITY_ID: list(self.entities.keys())[0],
                        "transition": self.default_transition,
                    }
            else:
                data = {
                    ATTR_ENTITY_ID: list(self.entities.keys())[0],
                    "transition": self.default_transition,
                }
        # data = {ATTR_ENTITY_ID: list(self.entities.keys())[0], "transition": 0.1}

        # Copy over handled attributes and disable RightLight for color/colormode/colortemp attribute usage cases
        if ATTR_BRIGHTNESS in kwargs:
            data[ATTR_BRIGHTNESS] = kwargs[ATTR_BRIGHTNESS]
        # if ATTR_TRANSITION in kwargs:
        #    data[ATTR_TRANSITION] = kwargs[ATTR_TRANSITION]

        for this_attr in [
            ATTR_HS_COLOR,
            ATTR_RGB_COLOR,
            ATTR_COLOR_TEMP,
            ATTR_COLOR_MODE,
        ]:
            if this_attr in kwargs:
                rl = False
                data[this_attr] = kwargs[this_attr]

        # Override RightLight mode if specificied
        if ATTR_EFFECT in kwargs:
            rl = True
            rlmode = kwargs[ATTR_EFFECT]
        else:
            rlmode = "Normal"
        self._curr_effect = rlmode

        if self._debug:
            _LOGGER.debug(f"{self.name} LIGHT ASYNC_TURN_ON: Data: {data}")

        f, r = self.getEntityNames()

        # Disable RightLight for other entities before turning on main entity
        for ent in r:
            await self.entities[ent].disable()

        # Assume first entity if for below threhold if not explicitly set
        if len(self.entities_below_threshold) > 0:
            b_ents = self.entities_below_threshold
        else:
            b_ents = [f]

        # Assume all other entities are for above threhold if not explcitly set
        if len(self.entities_above_threshold) > 0:
            a_ents = self.entities_above_threshold
        else:
            if len(r) > 0:
                # a_ents = [r[0]]
                a_ents = r
            else:
                a_ents = []

        for ent in b_ents:
            if rl:
                # Turn on light using RightLight
                if self.has_brightness_threshold:
                    if ent in self.brightness_multiplier:
                        thisbr = self._brightnessBT * self.brightness_multiplier[ent]
                    else:
                        thisbr = self._brightnessBT
                else:
                    if ent in self.brightness_multiplier:
                        thisbr = self._brightness * self.brightness_multiplier[ent]
                    else:
                        thisbr = self._brightness

                if self._debug:
                    _LOGGER.debug(
                        f"{self.name} LIGHT ASYNC_TURN_ON: BT RL turning on {ent}"
                    )

                await self.entities[ent].turn_on(
                    brightness=thisbr,
                    brightness_override=self._brightness_override,
                    mode=rlmode,
                    transition=data["transition"],
                )
            else:
                # Use for other modes, like specific color or temperatures
                if self._debug:
                    _LOGGER.debug(
                        f"{self.name} LIGHT ASYNC_TURN_ON: BT RL_specific turning on {ent}"
                    )
                await self.entities[ent].turn_on_specific(data)

        if self.has_brightness_threshold:
            for ent in a_ents:
                # Process remaining entities if over brightness threshold
                if rl:
                    # Turn on next entity using RightLight
                    if self._brightnessAT == 0:
                        if self._debug:
                            _LOGGER.debug(
                                f"{self.name} LIGHT ASYNC_TURN_ON: AT RL turning off {ent}"
                            )
                        await self.entities[ent].disable_and_turn_off()
                    else:
                        if ent in self.brightness_multiplier:
                            thisbr = (
                                self._brightnessAT * self.brightness_multiplier[ent]
                            )
                        else:
                            thisbr = self._brightnessAT

                        if self._debug:
                            _LOGGER.debug(
                                f"{self.name} LIGHT ASYNC_TURN_ON: AT RL turning on {ent}"
                            )
                        await self.entities[ent].turn_on(
                            brightness=thisbr,
                            brightness_override=self._brightness_override,
                            mode=rlmode,
                            transition=data["transition"],
                        )
                else:
                    # Use for other modes, like specific color or temperatures
                    if self._debug:
                        _LOGGER.debug(
                            f"{self.name} LIGHT ASYNC_TURN_ON: AT RL_specific turning on {ent}"
                        )
                    await self.entities[ent].turn_on_specific(data)

        self.async_schedule_update_ha_state(force_refresh=True)

    def getEntityNames(self):
        """Split entity key list into first (default) and rest list"""
        k = list(self.entities.keys())
        return k[0], k[1:]

    async def async_turn_on_mode(self, **kwargs: Any) -> None:
        """Turn on one of RightLight's color modes"""
        self._mode = kwargs.get("mode", "Vivid")
        self._is_on = True
        self._brightness = 255
        self._switched_on = True

        f, r = self.getEntityNames()
        # Disable RightLight for other entities before turning on main entity
        for ent in r:
            await self.entities[ent].disable()
        if self._debug:
            _LOGGER.debug(
                f"{self.name} LIGHT ASYNC_TURN_ON_MODE turning on {f} to mode {self._mode}"
            )
        await self.entities[f].turn_on(mode=self._mode)

        self.async_schedule_update_ha_state(force_refresh=True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Instruct the light to turn off, conditionally."""
        self._occupancy = any(self._occupancies.values())
        self._full_brightness_occupancy = any(self._full_brightness_occupancies.values())

        if self._debug:
            _LOGGER.debug(
                f"{self.name} LIGHT ASYNC_TURN_OFF: {kwargs, self._switched_on, self._occupancy, self._full_brightness_occupancy}"
            )

        # If the light wasn't switched on, or if there is no occupancy, turn off
        if (self._switched_on == False) or (self._occupancy == False):
            if self._debug:
                _LOGGER.debug(f"{self.name} LIGHT ASYNC_TURN_OFF: Turning off")
            await self._async_turn_off_helper(**kwargs)
        elif self._occupancy or self._full_brightness_occupancy:
            if self._debug:
                _LOGGER.debug(
                    f"{self.name} LIGHT ASYNC_TURN_OFF: Switching to motion sensor mode"
                )
            self._switched_on = False

            # Turn off if motion disable entites are on, otherwise switch to motion sensor mode
            if any(self.motion_disable_trackers.values()):
                await self._async_turn_off_helper(**kwargs)
            else:
                if self._full_brightness_occupancies:
                    await self.async_turn_on(
                        brightness=255, source="MotionSensor"
                    )
                else:
                    await self.async_turn_on(
                        brightness=self.motion_sensor_brightness, source="MotionSensor"
                    )

    async def _async_turn_off_helper(self, **kwargs: Any) -> None:
        """Instruct the light to turn off."""
        self._brightness = 0
        self._brightness_override = 0
        self._is_on = False
        self._switched_on = False
        self._mode = "Off"

        this_trans = self.default_transition
        if "source" in kwargs:
            if kwargs["source"] == "Switch":
                this_trans = self.switch_transition
            elif kwargs["source"] == "MotionSensor":
                this_trans = self.motion_sensor_transition

        if not "transition" in kwargs:
            kwargs["transition"] = this_trans

        f, r = self.getEntityNames()
        # Disable other entities before turning off main entity
        for ent in r:
            if self._debug:
                _LOGGER.debug(
                    f"{self.name} LIGHT ASYNC_TURN_OFF_HELPER turning off {ent}"
                )
            await self.entities[ent].disable_and_turn_off(**kwargs)
        if self._debug:
            _LOGGER.debug(f"{self.name} LIGHT ASYNC_TURN_OFF_HELPER turning off {f}")
        await self.entities[f].disable_and_turn_off(**kwargs)

        self.async_schedule_update_ha_state(force_refresh=True)

    async def up_brightness(self, **kwargs) -> None:
        """Increase brightness by one step"""
        if self._brightness == None:
            self._brightness = self.brightness_step
        elif self._brightness > (255 - self.brightness_step):
            self._brightness = 255
            self._brightness_override = self._brightness_override + self.brightness_step
        else:
            self._brightness = self._brightness + self.brightness_step

        await self.async_turn_on(brightness=self._brightness, **kwargs)

    async def down_brightness(self, **kwargs) -> None:
        """Decrease brightness by one step"""
        if self._brightness == None:
            await self.async_turn_off(**kwargs)
        elif self._brightness_override > 0:
            self._brightness_override = 0
            await self.async_turn_on(brightness=self._brightness, **kwargs)
        elif self._brightness < self.brightness_step:
            await self.async_turn_off(**kwargs)
        else:
            self._brightness = self._brightness - self.brightness_step
            await self.async_turn_on(brightness=self._brightness, **kwargs)

    async def async_update(self):
        """Query light and determine the state."""
        # if self._debug:
        #    _LOGGER.debug(f"{self.name} LIGHT ASYNC_UPDATE")

        f, r = self.getEntityNames()
        state = self.hass.states.get(f)

        if state == None:
            return

        self._hs_color = state.attributes.get(ATTR_HS_COLOR, self._hs_color)
        self._rgb_color = state.attributes.get(ATTR_RGB_COLOR, self._rgb_color)
        self._color_temp = state.attributes.get(ATTR_COLOR_TEMP, self._color_temp)
        self._min_mireds = state.attributes.get(ATTR_MIN_MIREDS, 154)
        self._max_mireds = state.attributes.get(ATTR_MAX_MIREDS, 500)
        # self._effect_list = state.attributes.get(ATTR_EFFECT_LIST)

        # Reload JSON buttonmap regularly
        if os.path.exists(self._button_map_file):
            ts = os.path.getmtime(self._button_map_file)
            if ts > self._button_map_timestamp:
                if self._debug:
                    _LOGGER.debug(f"{self.name} loading JSON button map file")

                def loadJSON():
                    return json.load(open(self._button_map_file))

                loop = asyncio.get_running_loop()
                self._button_map_data = await loop.run_in_executor(None, loadJSON)
                self._button_map_timestamp = ts

    @callback
    async def switch_message_received(self, mqttmsg) -> None:
        # async def switch_message_received(self, topic: str, payload: str, qos: int) -> None:
        """A new MQTT message has been received."""
        if ":" in self.switch:
            dev = mqttmsg.data.get("device_ieee")
            if dev != self.switch:
                return
            payload = mqttmsg.data.get("command")
            if self._debug:
                _LOGGER.debug(f"{self.name} switch: {payload}")
        else:
            topic, payload, qos = mqttmsg.topic, mqttmsg.payload, mqttmsg.qos
            if self._debug:
                _LOGGER.debug(f"{self.name} switch: {topic}, {payload}, {qos}")

        if "release" in payload:
            return

        if ("hold" in payload) and (payload in self._button_map_data):
            # JSON found for this button press
            config_list = self._button_map_data[payload]
            this_list = config_list[self._buttonCounts[payload]]

            # Increment button count and loop to zero.  Zero out the other buttons' counts
            self._buttonCounts[payload] += 1
            if self._buttonCounts[payload] >= len(config_list):
                self._buttonCounts[payload] = 0
            for key in self._buttonCounts.keys():
                if key != payload:
                    self._buttonCounts[key] = 0

            for command in this_list:
                self._switched_on = True

                if self._debug:
                    _LOGGER.error(f"{self.name} JSON Switch command: {command}")
                if command[0] == "Brightness":
                    ent = command[1]
                    br = command[2]

                    if br == 0:
                        await self.hass.services.async_call(
                            "light", "turn_off", {"entity_id": ent}
                        )
                    else:
                        await self.hass.services.async_call(
                            "light", "turn_on", {"entity_id": ent, "brightness": br}
                        )
                elif command[0] == "RightLight":
                    ent = command[1]
                    val = command[2]

                    if not ent in self.entities:
                        self.entities[ent] = RightLight(ent, self.hass, self._debug_rl)

                    rl = self.entities[ent]

                    if val == "Disable":
                        await rl.disable()
                    elif val in rl.getColorModes():
                        await rl.turn_on(mode=val)
                    elif (val == 0) or (val == "Off"):
                        await rl.disable_and_turn_off()
                    else:
                        await rl.turn_on(brightness=val, brightness_override=0)
                elif command[0] == "Color":
                    ent = command[1]
                    r, g, b = command[2:]
                    br = sum([r, g, b]) / 3

                    if not ent in self.entities:
                        self.entities[ent] = RightLight(ent, self.hass, self._debug_rl)

                    rl = self.entities[ent]
                    await rl.turn_on_specific(
                        {"entity_id": ent, "rgb_color": [r, g, b], "brightness": br}
                    )

                elif command[0] == "Scene":
                    await self.hass.services.async_call(
                        "scene", "turn_on", {"entity_id": command[1]}
                    )
                else:
                    _LOGGER.error(
                        f"{self.name} error - unrecognized button_map.json command type: {command[0]}"
                    )

        elif payload.startswith("on"):  # and "press" in payload:
            self.clearButtonCounts()
            self._brightness_override = 0
            await self.async_turn_on(source="Switch", brightness=255)
        elif payload.startswith("up"):  # and "press" in payload:
            self.clearButtonCounts()
            await self.up_brightness(source="Switch")
        elif payload.startswith("down"):  # and "press" in payload:
            self.clearButtonCounts()
            await self.down_brightness(source="Switch")
        elif payload.startswith("off"):  # and "press" in payload:
            self.clearButtonCounts()
            await self.async_turn_off(source="Switch")
        else:
            if self._debug:
                _LOGGER.error(f"{self.name} switch handler fail: {payload}")

    def clearButtonCounts(self):
        for key in self._buttonCounts.keys():
            self._buttonCounts[key] = 0

    #    @callback
    #    async def json_switch_message_received(
    #        self, topic: str, payload: str, qos: int
    #    ) -> None:
    #        """A new MQTT message has been received."""
    #        if payload in self._button_map_data.keys():
    #            config_list = self._button_map_data[payload]
    #            this_list = config_list[self._buttonCounts[payload]]
    #
    #            # Increment button count and loop to zero.  Zero out the rest
    #            self._buttonCounts[payload] += 1
    #            if self._buttonCounts[payload] >= len(config_list):
    #                self._buttonCounts[payload] = 0
    #            for key in self._buttonCounts.keys():
    #                if key != payload:
    #                    self._buttonCounts[key] = 0
    #
    #            for command in this_list:
    #                if self._debug:
    #                    _LOGGER.error(f"{self.name} JSON Switch command: {command}")
    #                if command[0] == "Brightness":
    #                    ent = command[1]
    #                    br = command[2]
    #
    #                    if br == 0:
    #                        await self.hass.services.async_call(
    #                            "light", "turn_off", {"entity_id": ent}
    #                        )
    #                    else:
    #                        await self.hass.services.async_call(
    #                            "light", "turn_on", {"entity_id": ent, "brightness": br}
    #                        )
    #                elif command[0] == "RightLight":
    #                    ent = command[1]
    #                    val = command[2]
    #
    #                    if not ent in self.entities:
    #                        self.entities[ent] = RightLight(ent, self.hass, self._debug_rl)
    #                        # _LOGGER.error(f"{self.name} error: Unknown entity '{ent}' in button_map.json.  Should be one of: {self.entities.keys()}")
    #                        # continue
    #
    #                    rl = self.entities[ent]
    #
    #                    if val == "Disable":
    #                        await rl.disable()
    #                    elif val in rl.getColorModes():
    #                        await rl.turn_on(mode=val)
    #                    elif (val == 0) or (val == "Off"):
    #                        await rl.disable_and_turn_off()
    #                    else:
    #                        await rl.turn_on(brightness=val, brightness_override=0)
    #                elif command[0] == "Scene":
    #                    if self._debug:
    #                        _LOGGER.error(f"{self.name} JSON Switch Scene: {command[1]}")
    #                    await self.hass.services.async_call(
    #                        "scene", "turn_on", {"entity_id": command[1]}
    #                    )
    #                else:
    #                    _LOGGER.error(
    #                        f"{self.name} error - unrecognized button_map.json command type: {command[0]}"
    #                    )

    @callback
    async def motion_sensor_message_received(self, mqttmsg) -> None:
        """A new MQTT message has been received."""
        # async def motion_sensor_message_received( self, topic: str, payload: str, qos: int) -> None:
        topic, payload, qos = mqttmsg.topic, mqttmsg.payload, mqttmsg.qos

        payload = json.loads(payload)
        z, ms = topic.split("/")

        if not ms in self._occupancies and not ms in self._full_brightness_occupancies:
            _LOGGER.error(f"{self.name}: Unexpected motion sensor name: {ms}")
            return

        if ms in self.motion_sensors:
            if self._occupancies[ms] == payload["occupancy"]:
                # No change to state
                return
        else:
            if self._full_brightness_occupancies[ms] == payload["occupancy"]:
                # No change to state
                return

        if self._debug:
            _LOGGER.error(f"{self.name} motion sensor: {topic}, {payload}, {qos}")

        if ms in self.motion_sensors:
            self._occupancies[ms] = payload["occupancy"]
            self._occupancy = any(self._occupancies.values())
        else:
            self._full_brightness_occupancies[ms] = payload["occupancy"]
            self._full_brightness_occupancy = any(self._full_brightness_occupancies.values())

        if self._debug:
            _LOGGER.debug(
                f"{self.name} motion sensor: Occ: {self._occupancies} => {self._occupancy}"
                f"{self.name} motion sensor: FBOcc: {self._full_brightness_occupancies} => {self._full_brightness_occupancy}"
            )

        # Disable motion sensor tracking if the lights are switched on or the harmony is on
        # if self._switched_on or ((self.harmony_entity != None) and self._harmony_on):
        #    return

        # 3/10/24 - Moving this into the 'if' block below so turn_off still happens
        #if self._switched_on or any(self.motion_disable_trackers.values()):
        if self._switched_on:
            return

        if self._occupancy or self._full_brightness_occupancy:
            if any(self.motion_disable_trackers.values()):
                return
            if self._full_brightness_occupancy:
                await self.async_turn_on(
                    brightness=255, source="MotionSensor"
                )
            else:
                await self.async_turn_on(
                    brightness=self.motion_sensor_brightness, source="MotionSensor"
                )
        else:
            await self.async_turn_off(source="MotionSensor")

    @callback
    async def motion_sensor_message_received_zha(self, ev) -> None:
        if self._debug:
            _LOGGER.debug(f"{self.name} motion sensor: {ev}")
        payload = ev.data.get("new_state").state
        dev = ev.data.get("entity_id")
        if self._debug:
            _LOGGER.debug(f"{self.name} motion sensor payload: {payload}")

        payload = payload == "on"

        if not dev in self._occupancies and not dev in self._full_brightness_occupancies:
            _LOGGER.error(f"{self.name}: Unexpected ZHA motion sensor name: {dev}")
            return

        """A new MQTT message has been received."""
        if dev in self.motion_sensors:
            if self._occupancies[dev] == payload:
                # No change to state
                return
        else:
            if self._full_brightness_occupancies[dev] == payload:
                # No change to state
                return

        if dev in self.motion_sensors:
            self._occupancies[dev] = payload
            self._occupancy = any(self._occupancies.values())
        else:
            self._full_brightness_occupancies[dev] = payload
            self._full_brightness_occupancy = any(self._full_brightness_occupancies.values())

        if self._debug:
            _LOGGER.debug(
                f"{self.name} motion sensor: Occ: {self._occupancies} => {self._occupancy}"
            )

        # Disable motion sensor tracking if the lights are switched on a motion_disable_entity is on
        # if self._switched_on or ((self.harmony_entity != None) and self._harmony_on):
        #    return
        if self._switched_on or any(self.motion_disable_trackers.values()):
            return

        if self._full_brightness_occupancy:
            await self.async_turn_on(
                brightness=255, source="MotionSensor"
            )
        elif self._occupancy:
            await self.async_turn_on(
                brightness=self.motion_sensor_brightness, source="MotionSensor"
            )
        else:
            await self.async_turn_off(source="MotionSensor")

    # @callback
    # async def harmony_update(self, this_event):
    #    """Track harmony updates"""
    #    ev = this_event.as_dict()
    #    ns = ev["data"]["new_state"].state
    #    if ns == "on":
    #        self._harmony_on = True
    #    else:
    #        self._harmony_on = False

    @callback
    async def motion_disable_entity_update(self, this_event):
        """Track updates on motion_disable_entities"""
        ev = this_event.as_dict()
        if self._debug:
            _LOGGER.debug(f"{self.name}: motion_disable_entitiy_update: {ev}")

        ent = ev["data"]["entity_id"]
        ns = ev["data"]["new_state"].state
        if ns == "on":
            self.motion_disable_trackers[ent] = True
        else:
            self.motion_disable_trackers[ent] = False

    @callback
    async def other_entity_update(self, this_event):
        """Track events of other entities"""
        ev = this_event.as_dict()
        if self._debug:
            _LOGGER.error(f"{self.name} other entity update: {ev}")

        ent = ev["data"]["entity_id"]
        ns = ev["data"]["new_state"].state

        if "brightness" in ev["data"]["new_state"].attributes:
            br = ev["data"]["new_state"].attributes["brightness"]
        else:
            br = 255

        if ns == "on":
            # Grab other light's brightness
            self._others[ent] = br

            # -1 brightness value in 'other' array means to copy brightness from that entity
            if self.other_light_trackers[ent] == -1:
                this_br = br
            else:
                this_br = self.other_light_trackers[ent]

            ## Turn on if not already on or new other light is brighter
            # if (self._is_on == False) or (self._brightness < this_br):
            #    await self.async_turn_on(brightness=this_br)
            await self.async_turn_on(brightness=this_br)

            # Feature to turn off other lights when this light goes on
            if self.turn_off_other_lights:
                await self.hass.services.async_call(
                    "light", "turn_off", {"entity_id": ent}
                )
        elif self.track_other_light_off_events and ns == "off":
            self._others[ent] = False

            if not any(self._others.values()):
                await self.async_turn_off()
