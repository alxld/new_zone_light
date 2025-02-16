"""New version of New Light than also supports Zones"""
#from __future__ import annotations
#
#from homeassistant.helpers import config_validation as cv
#import voluptuous as vol
#
#DOMAIN = "new_zone_light"
#
#CONF_NAME = "name"
#CONF_UNIQUE_ID= "unique_id"
#CONF_ENTITIES = "entities"
#CONF_SWITCHES = "switch"
#CONF_HAS_BRIGHTNESS_THRESHOLD = "has_brightness_threshold"
#
#PLATFORM_SCHEMA = vol.Schema(
#    {
#        #vol.Required(CONF_PLATFORM): "NewZoneLight",
#        vol.Required(CONF_NAME): cv.string,
#        vol.Required(CONF_UNIQUE_ID): cv.string,
#        vol.Required(CONF_ENTITIES): cv.entity_ids,
#        vol.Optional(CONF_SWITCHES): cv.string,
#        vol.Optional(CONF_HAS_BRIGHTNESS_THRESHOLD): cv.boolean,
#    }
#)
#
#def setup(hass, config):
#    return True