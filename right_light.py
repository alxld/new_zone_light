from homeassistant.helpers import entity
from homeassistant.helpers.event import async_call_later
from homeassistant.core import HomeAssistant, callback
from homeassistant.util import dt
import logging, random, asyncio
from suntime import Sun
from datetime import date, timedelta


class RightLight:
    """RightLight object to control a single light or light group"""
    validate_delay = 2 # Seconds to wait before validating a change
    validate_brightness_threshold = 10  # Brightness difference to consider a change valid
    validate_ct_threshold = 10  # Color temperature difference to consider a change valid
    validate_color_threshold = 30  # Color difference to consider a change valid (per RGB channel)
    trans_delay_min = 5  # Minimum seconds for a transition
    trans_delay_max = 15  # Maximum seconds for a transition

    def __init__(self, ent: entity, hass: HomeAssistant, debug=False) -> None:
        self._entity = ent
        self._hass = hass
        self._debug = debug

        self._mode = "Off"
        self.today = None

        self._logger = logging.getLogger(f"RightLight({self._entity})")


        self.trip_points = {}

        state = self._hass.states.get(self._entity)
        self._ct_high = 5000
        self._ct_max = 5000
        self._ct_min = 2000
        self._ct_scalar = 0.35

        self._br_over_ct_mult = 6

        self.on_transition = 0.2
        self.on_color_transition = 0.2
        self.off_transition = 0.2
        self.dim_transition = 0.2

        # Store callback for cancelling scheduled next event
        self._currSched = []

        cd = self._hass.config.as_dict()
        self.sun = Sun(cd["latitude"], cd["longitude"])

        self._getNow()

        async def updateMaxMin(_):
            state = self._hass.states.get(self._entity)
            self._ct_max = state.attributes.get("max_color_temp_kelvin", self._ct_max)
            self._ct_min = state.attributes.get("min_color_temp_kelvin", self._ct_min)
            if self._debug:
                self._logger.error(f"updateMaxMin: {self._ct_min}, {self._ct_max}")

        async_call_later(self._hass, 10, updateMaxMin)

    async def turn_on(self, **kwargs) -> None:
        """
        Turns on a RightLight-controlled entity

        :key brightness: The master brightness control
        :key brightness_override: Additional brightness to add on to RightLight's calculated brightness
        :key mode: One of the trip_point key names (Normal, Vivid, Fun1, Fun2, Bright, One, Two)
        :key transition: Transition time to use for this turn_on
        :key valmode: If True, verify that the lights turned on, then start the next transition.
                      If False, schedule the first transition and a later turn_on with valmode=True
        :key nocancel: If True, do not cancel any pending scheduled events. Used when scheduling a new turn_on
        """
        # Cancel any pending eventloop schedules
        nocancel = kwargs.get("nocancel", False)
        if not nocancel:
            self._cancelSched()

        self._getNow()

        self._mode = kwargs.get("mode", "Normal")
        self._brightness = kwargs.get("brightness", 255)
        self._brightness_override = kwargs.get("brightness_override", 0)
        this_transition = kwargs.get("transition", self.on_transition)
        this_valmode = kwargs.get("valmode", False)

        if self._debug:
            self._logger.error(f"RightLight turn_on: {kwargs}")
            self._logger.error(
                f"RightLight turn_on: {self._mode}, {self._brightness}, {self._brightness_override}"
            )

        # Turning on to 0 brightness is translated into a turn_off
        if self._brightness == 0:
            await self.disable_and_turn_off(**kwargs)
            return

        # Find trip points around current time
        for next_idx in range(0, len(self.trip_points[self._mode])):
            if self.trip_points[self._mode][next_idx][0] >= self.now:
                break
        prev_idx = next_idx - 1

        # Calculate how far through the trip point span we are now
        prev_time = self.trip_points[self._mode][prev_idx][0]
        next_time = self.trip_points[self._mode][next_idx][0]
        time_ratio = (self.now - prev_time) / (next_time - prev_time)
        time_rem = (next_time - self.now).seconds

        if self._debug:
            self._logger.error(f"Now: {self.now}")
            self._logger.error(
                f"Prev/Next: {prev_idx}, {next_idx}, {prev_time}, {next_time}, {time_ratio}"
            )

        if self._mode == "Normal":
            # Compute br/ct for previous point
            br_max_prev = self.trip_points["Normal"][prev_idx][1][1] / 255
            br_prev = br_max_prev * (self._brightness + self._brightness_override)

            ct_max_prev = self.trip_points["Normal"][prev_idx][1][0]
            ct_delta_prev = (self._ct_high - ct_max_prev) * (1 - br_max_prev) * self._ct_scalar
            ct_prev = ct_max_prev - ct_delta_prev

            # Compute br/ct for next point
            br_max_next = self.trip_points["Normal"][next_idx][1][1] / 255
            br_next = br_max_next * (self._brightness + self._brightness_override)

            ct_max_next = self.trip_points["Normal"][next_idx][1][0]
            ct_delta_next = (self._ct_high - ct_max_next) * (1 - br_max_next) * self._ct_scalar
            #self._logger.error(f"ct_max_next: {ct_max_next}, ct_delta_next: {ct_delta_next}, br_max_next: {br_max_next}")
            #self._logger.error(f"ct_high: {self._ct_high}, ct_scalar: {self._ct_scalar}")
            ct_next = ct_max_next - ct_delta_next
            if ct_next < self._ct_min:
                ct_next = self._ct_min
            if ct_prev < self._ct_min:
                ct_prev = self._ct_min
            if ct_next > self._ct_max:
                ct_next = self._ct_max
            if ct_prev > self._ct_max:
                ct_prev = self._ct_max

            if self._debug:
                self._logger.error(f"Prev/Next: {br_prev}/{ct_prev} => {br_next}/{ct_next}")

            # Scale linearly to current time
            br = (br_next - br_prev) * time_ratio + br_prev
            ct = (ct_next - ct_prev) * time_ratio + ct_prev
            br = int(round(br, 0))
            ct = int(round(ct, 0))
            br_next = int(round(br_next, 0))
            ct_next = int(round(ct_next, 0))

            # Brightnesses above 255 are clamped, but color temperature will continue to increase
            if br > 255:
                br_over = br - 255
                br = 255
                ct = ct + br_over * self._br_over_ct_mult
            if br_next > 255:
                br_next_over = br_next - 255
                br_next = 255
                ct_next = ct_next + br_next_over * self._br_over_ct_mult
            if ct > self._ct_max:
                ct = self._ct_max
            if ct_next > self._ct_max:
                ct_next = self._ct_max

            if self._debug:
                self._logger.error(f"Final: {br}/{ct} -> {time_rem}sec")

            async def turn_on_now(_):
                if self._debug:
                    self._logger.error(f"turn_on_now start.  br/ct: {br}/{ct}, transition: {this_transition}")
                await self._hass.services.async_call(
                    "light",
                    "turn_on",
                    {
                        "entity_id": self._entity,
                        "brightness": br,
                        "color_temp_kelvin": ct,
                        "transition": this_transition,
                    },
                    blocking=True,
                )
                if self._debug:
                    self._logger.error(f"turn_on_now done")

            #async def turn_on_now(_):
            #    state = self._hass.states.get(self._entity)
            #    bulb_was_off = state is None or state.state != "on"
            #    if bulb_was_off:
            #        await self._hass.services.async_call(
            #            "light", "turn_on",
            #            {"entity_id": self._entity},
            #            blocking=True,
            #        )
            #        await asyncio.sleep(0.1)
            #    await self._hass.services.async_call(
            #        "light", "turn_on",
            #        {
            #            "entity_id": self._entity,
            #            "brightness": br,
            #            "color_temp_kelvin": ct,
            #            "transition": this_transition,
            #        },
            #        blocking=True,
            #    )

            async def turn_on_next(_):
                if self._debug:
                    self._logger.error(f"turn_on_next start.  br/ct: {br_next}/{ct_next}, transition: {time_rem}")
                remaining = max(0, int(round((next_time - dt.now()).total_seconds())))
                await self._hass.services.async_call(
                    "light",
                    "turn_on",
                    {
                        "entity_id": self._entity,
                        "brightness": br_next,
                        "color_temp_kelvin": ct_next,
                        "transition": remaining,
                    },
                    blocking=True,
                )
                if self._debug:
                    self._logger.error(f"turn_on_next done")

            async def reschedule_turn_on(_):
                if self._debug:
                    self._logger.error(f"reschedule_turn_on start")
                await self.turn_on(
                    brightness=self._brightness,
                    brightness_override=self._brightness_override,
                    mode=self._mode,
                    valmode=True,
                    nocancel=False,
                )
                if self._debug:
                    self._logger.error(f"reschedule_turn_on done")

            async def schedule_next_turn_on(_):
                if self._debug:
                    self._logger.error(f"schedule_next_turn_on start")
                await self.turn_on(
                    brightness=self._brightness,
                    brightness_override=self._brightness_override,
                    mode=self._mode,
                    valmode=False,
                    nocancel=False,
                )
                if self._debug:
                    self._logger.error(f"schedule_next_turn_on done")

            if this_valmode:
                # In validation mode, verify the entity is on and at the correct brightness and color temp
                # If it's on, schedule the next transitions
                # If it's not, turn it on again and schedule another validation

                # Verify current state against intended state
                state = self._hass.states.get(self._entity)
                state_is_correct = (state is not None and state.state == "on")
                if state_is_correct:
                    br_is_correct = abs(state.attributes.get("brightness", -1) - br) < RightLight.validate_brightness_threshold
                    ct_is_correct = abs(state.attributes.get("color_temp_kelvin", -1) - ct) < RightLight.validate_ct_threshold
                else:
                    br_is_correct = False
                    ct_is_correct = False
                is_correct = state_is_correct and br_is_correct and ct_is_correct

                if self._debug:
                    self._logger.error(f"Valmode: State: {state}, is_correct: {is_correct} (st: {state_is_correct}, br: {br_is_correct}, ct: {ct_is_correct})")

                if is_correct:
                    # Entity is on and at the correct brightness/color temp, so schedule the next transitions

                    # Transition to next values
                    ret = async_call_later(self._hass, random.randint(RightLight.trans_delay_min, RightLight.trans_delay_max), turn_on_next)
                    self._addSched(ret)

                    # Schedule another turn_on at next_time to start the next transition
                    # Add 1 second to ensure next event is after trigger point
                    remaining = max(0, int(round((next_time - dt.now()).total_seconds())))
                    ret = async_call_later(self._hass, remaining + 1, schedule_next_turn_on)
                    self._addSched(ret)
                else:
                    # Entity is not correct, so turn it on and reschedule validation
                    #if not ct_is_correct:
                    #    # Set color temp first if needed
                    #    ret = async_call_later(self._hass, 0, set_color_temp)
                    #    self._addSched(ret)

                    #if not br_is_correct:
                    #    # If brightness is wrong, turn on the light
                    #    ret = async_call_later(self._hass, 0.25, turn_on_now)
                    #    self._addSched(ret)

                    if self._debug:
                        self._logger.error(f"Valmode: Re-turning on")
                    ret = async_call_later(self._hass, 0, turn_on_now)
                    self._addSched(ret)

                    if self._debug:
                        self._logger.error(f"Valmode: Re-scheduling")
                    # Schedule another validation
                    ret = async_call_later(self._hass, this_transition + RightLight.validate_delay, reschedule_turn_on)
                    self._addSched(ret)
            else:
                # Not in validation mode, so turn on the light and schedule the validation

                ## Set color temp first
                #ret = async_call_later(self._hass, 0, set_color_temp)
                #self._addSched(ret)

                # Turn on the light
                ret = async_call_later(self._hass, 0.25, turn_on_now)
                self._addSched(ret)

                # Schedule another call to turn_on with same parameters but valmode=True
                ret = async_call_later(self._hass, this_transition + RightLight.validate_delay, reschedule_turn_on)
                self._addSched(ret)

        else: # Color mode

            prev_rgb = self.trip_points[self._mode][prev_idx][1]
            next_rgb = self.trip_points[self._mode][next_idx][1]

            if self._debug:
                self._logger.error(f"Prev/Next: {prev_rgb}/{next_rgb}")

            r_now = prev_rgb[0] + (next_rgb[0] - prev_rgb[0]) * time_ratio
            g_now = prev_rgb[1] + (next_rgb[1] - prev_rgb[1]) * time_ratio
            b_now = prev_rgb[2] + (next_rgb[2] - prev_rgb[2]) * time_ratio
            now_rgb = [r_now, g_now, b_now]

            if self._debug:
                self._logger.error(f"Final: {now_rgb} -> {time_rem}sec")

            # Define callback helpers
            async def turn_on_rgb_now(_):
                if self._debug:
                    self._logger.error(f"turn_on_rgb_now start")
                await self._hass.services.async_call(
                    "light",
                    "turn_on",
                    {
                        "entity_id": self._entity,
                        "brightness": self._brightness,
                        "rgb_color": now_rgb,
                        "transition": this_transition,
                    },
                    blocking=True,
                )
                if self._debug:
                    self._logger.error(f"turn_on_rgb_now done")

            async def turn_on_rgb_next(_):
                if self._debug:
                    self._logger.error(f"turn_on_rgb_next start")
                remaining = max(0, int(round((next_time - dt.now()).total_seconds())))
                await self._hass.services.async_call(
                    "light",
                    "turn_on",
                    {
                        "entity_id": self._entity,
                        "brightness": self._brightness,
                        "rgb_color": next_rgb,
                        "transition": remaining,
                    },
                    blocking=True,
                )
                if self._debug:
                    self._logger.error(f"turn_on_rgb_next done")

            async def reschedule_rgb_turn_on(_):
                if self._debug:
                    self._logger.error(f"reschedule_rgb_turn_on start")
                await self.turn_on(
                    brightness=self._brightness,
                    mode=self._mode,
                    valmode=True,
                    nocancel=False,
                )
                if self._debug:
                    self._logger.error(f"reschedule_rgb_turn_on done")

            async def schedule_next_rgb_turn_on(_):
                if self._debug:
                    self._logger.error(f"schedule_next_rgb_turn_on start")
                await self.turn_on(
                    brightness=self._brightness,
                    mode=self._mode,
                    valmode=False,
                    nocancel=False,
                )
                if self._debug:
                    self._logger.error(f"schedule_next_rgb_turn_on done")

            if this_valmode:
                # In validation mode, verify that the lights turned on and to the correct color, then start the next transition.
                # If not, turn it on again and schedule another validation

                state = self._hass.states.get(self._entity)
                is_correct = (state is not None and state.state == "on")
                # Check brightness and color temp
                if is_correct and "rgb_color" in state.attributes:
                    is_correct = is_correct and all(
                        abs(state.attributes["rgb_color"][i] - now_rgb[i]) < RightLight.validate_color_threshold for i in range(3)
                    )

                if self._debug:
                    self._logger.error(f"Valmode: State: {state}, is_correct: {is_correct}")

                if is_correct:
                    # Entity is on and at the correct color, so schedule the next transitions

                    # Transition to next values
                    if self._debug:
                        self._logger.error(f"Valmode: Transitioning to next color ({next_rgb} in {time_rem}sec)")
                    ret = async_call_later(self._hass, 0, turn_on_rgb_next)
                    self._addSched(ret)

                    # Schedule another turn_on at next_time to start the next transition
                    # Add 1 second to ensure next event is after trigger point
                    if self._debug:
                        self._logger.error(f"Valmode: Scheduling next color change at {next_time}")
                    remaining = max(0, int(round((next_time - dt.now()).total_seconds())))
                    ret = async_call_later(self._hass, remaining + 1, schedule_next_rgb_turn_on)
                    self._addSched(ret)
                else:
                    # Entity is not correct, so turn it on again and reschedule validation
                    if self._debug:
                        self._logger.error(f"Valmode: Re-turning on")
                    ret = async_call_later(self._hass, 0, turn_on_rgb_now)
                    self._addSched(ret)

                    if self._debug:
                        self._logger.error(f"Valmode: Re-scheduling")
                    # Schedule another validation
                    ret = async_call_later(self._hass, this_transition + 1, reschedule_rgb_turn_on)
                    self._addSched(ret)
            else:
                # Not in validation mode, so turn on the light and schedule the validation
                ret = async_call_later(self._hass, 0, turn_on_rgb_now)
                self._addSched(ret)

                # Schedule another call to turn_on with same parameters but valmode=True
                ret = async_call_later(self._hass, this_transition + 1, reschedule_rgb_turn_on)
                self._addSched(ret)


    # Helper function to be used to create a task and run a coroutine in the future
    async def delay_run(self, seconds, coro, *args, **kwargs):
        if self._debug:
            self._logger.error(
                f"delay_run: s:{seconds}, c:{coro}, a:{args}, k:{kwargs}"
            )
        await asyncio.sleep(seconds)
        # await self._hass.loop.sleep(seconds)
        await coro(*args, **kwargs)

    # async def _turn_on_specific(self, data) -> None:
    #    """Disables RightLight functionality and sets light to values in 'data' variable"""
    #    if self._debug:
    #        self._logger.error(f"_turn_on_specific: {data}")
    #    await self._hass.services.async_call("light", "turn_on", data)

    async def turn_on_specific(self, data) -> None:
        """External version of _turn_on_specific that runs twice to ensure successful transition"""
        if self._debug:
            self._logger.error(f"turn_on_specific: {data}")
        await self.disable()

        # Make a copy of data to avoid modifying the shared dict
        data = dict(data)
        
        if not "transition" in data:
            data["transition"] = self.on_transition
        if not "brightness" in data:
            data["brightness"] = 255

        # Ensure the data has the correct entity_id for this RightLight instance
        data["entity_id"] = self._entity

        # await self._turn_on_specific(data)
        await self._hass.services.async_call("light", "turn_on", data)

        # Removing second call - if things break, this may be why
        # self._hass.loop.call_later(
        #    0.6, self._hass.loop.create_task, self._turn_on_specific(data)
        # )

    async def disable_and_turn_off(self, **kwargs):
        """
        :key valmode: If True, verify that the lights turned off
                        If False, schedule a turn_off with valmode=True
        """
        # Cancel any pending eventloop schedules
        if self._debug:
            self._logger.error(f"turn_off")
        self._cancelSched()

        valmode = kwargs.get("valmode", False)

        self._brightness = 0

        async def turn_off_now(_):
            await self._hass.services.async_call(
                "light",
                "turn_off",
                {
                    "entity_id": self._entity,
                    "transition": kwargs.get("transition", self.off_transition),
                },
            )

        async def reschedule_turn_off(_):
            await self.disable_and_turn_off(valmode=True)

        if valmode:
            state = self._hass.states.get(self._entity)
            is_off = (state is None or state.state != "on")

            if self._debug:
                self._logger.error(f"Valmode: State: {state}, is_off: {is_off}")

            if not is_off:
                # Entity is not off, so turn it off
                ret = async_call_later(self._hass, 0, turn_off_now)
                self._addSched(ret)

                # Schedule another validation
                ret = async_call_later(self._hass, self.off_transition + RightLight.validate_delay, reschedule_turn_off)
                self._addSched(ret)
        else:
            ret = async_call_later(self._hass, 0, turn_off_now)
            self._addSched(ret)

            ret = async_call_later(self._hass, self.off_transition + RightLight.validate_delay, reschedule_turn_off)
            self._addSched(ret)

    async def disable(self):
        # Cancel any pending eventloop schedules
        self._cancelSched()

    def _cancelSched(self):
        if self._debug:
            self._logger.error(f"_cancelSched: {len(self._currSched)}")
        while self._currSched:
            ret = self._currSched.pop(0)
            if callable(ret):
                ret()
            else:
                ret.cancel()
        # for ret in self._currSched:
        #    ret.cancel()
        if self._debug:
            self._logger.error(f"_cancelSched End: {len(self._currSched)}")

    def _addSched(self, ret):
        # FIFO of event callbacks to ensure all are properly cancelled
        # if len(self._currSched) >= 3:
        #    self._currSched.pop(0)
        if self._debug:
            self._logger.error(f"_addSched: {len(self._currSched)}")
        self._currSched.append(ret)
        if self._debug:
            self._logger.error(f"_addSched End: {len(self._currSched)}")

    def _getNow(self):
        self.now = dt.now()
        rerun = date.today() != self.today
        self.today = date.today()

        if rerun:
            self.sunrise = dt.as_local(self.sun.get_sunrise_time())
            self.sunset = dt.as_local(self.sun.get_sunset_time())
            self.sunrise = self.sunrise.replace(
                day=self.now.day, month=self.now.month, year=self.now.year
            )
            self.sunset = self.sunset.replace(
                day=self.now.day, month=self.now.month, year=self.now.year
            )
            self.midnight_early = self.now.replace(
                microsecond=0, second=0, minute=0, hour=0
            )
            self.midnight_thirty = self.now.replace(
                #microsecond=0, second=0, minute=0, hour=0
                microsecond=0, second=0, minute=30, hour=0
            )
            self.ten_thirty = self.now.replace(
                microsecond=0, second=0, minute=30, hour=22
            )
            self.midnight_late = self.now.replace(
                microsecond=0, second=59, minute=59, hour=23
            )

            self.defineTripPoints()

    def defineTripPoints(self):
        self.trip_points["Normal"] = []
        timestep = timedelta(minutes=2)

        # In debug mode, add in drastic changes every two minutes to increase observability
        if self._debug == 2:
            debug_trip_points = [[2500, 120], [4000, 255]]
            self.trip_points["Normal"] = self.enumerateTripPoints(
                timestep / 8, debug_trip_points
            )
        else:
            self.trip_points["Normal"].append([self.midnight_early,                  [2500, 150]])  # Midnight night
            self.trip_points["Normal"].append([self.midnight_thirty,                 [2000, 10 ]])  # Midnight morning
            self.trip_points["Normal"].append([self.sunrise - timedelta(minutes=15), [2000, 10 ]])  # Sunrise - 15
            self.trip_points["Normal"].append([self.sunrise + timedelta(minutes=30), [4700, 255]])  # Sunrise + 30
            self.trip_points["Normal"].append([self.sunset  - timedelta(minutes=90), [4200, 255]])  # Sunset - 90
            self.trip_points["Normal"].append([self.sunset  - timedelta(minutes=30), [3200, 255]])  # Sunset - 30
            self.trip_points["Normal"].append([self.sunset,                          [3000, 255]])  # Sunset
            self.trip_points["Normal"].append([self.ten_thirty,                      [2700, 255]])  # 10:30
            self.trip_points["Normal"].append(self.trip_points["Normal"][0])  # Midnight night

        vivid_trip_points = [
            [255, 0, 0],
            [202, 0, 127],
            [130, 0, 255],
            [0, 0, 255],
            [0, 90, 190],
            [0, 200, 200],
            [0, 255, 0],
            [255, 255, 0],
            [255, 127, 0],
        ]

        bright_trip_points = [
            [255, 100, 100],
            [202, 80, 127],
            [150, 70, 255],
            [90, 90, 255],
            [60, 100, 190],
            [70, 200, 200],
            [80, 255, 80],
            [255, 255, 0],
            [255, 127, 70],
        ]

        calm_trip_points = [
            [255, 0, 0],
            [202, 0, 127],
            [130, 0, 255],
            [0, 0, 255],
            [0, 90, 190],
            [0, 200, 200],
            [0, 255, 0],
            [255, 127, 0],
        ]

        one_trip_points = [[0, 104, 255], [255, 0, 255]]

        two_trip_points = [[255, 0, 255], [0, 104, 255]]

        # Loop to create vivid trip points
        self.trip_points["Vivid"] = self.enumerateTripPoints(
            timestep, vivid_trip_points
        )

        # Faster timestep for Fun1 mode
        self.trip_points["Fun1"] = self.enumerateTripPoints(
            timestep / 8, vivid_trip_points
        )

        # Faster timestep for Fun2 mode, time shifted from Fun1
        self.trip_points["Fun2"] = self.enumerateTripPoints(
            timestep / 32, bright_trip_points[1:] + [bright_trip_points[0]]
        )

        # Loop to create bright trip points
        self.trip_points["Bright"] = self.enumerateTripPoints(
            timestep, bright_trip_points
        )

        # Loop to create calm trip points
        self.trip_points["Calm"] = self.enumerateTripPoints(timestep, calm_trip_points)

        # Loop to create 'one' trip points
        self.trip_points["One"] = self.enumerateTripPoints(timestep, one_trip_points)

        # Loop to create 'two' trip points
        self.trip_points["Two"] = self.enumerateTripPoints(timestep, two_trip_points)

    def getColorModes(self):
        return list(self.trip_points.keys())

    def enumerateTripPoints(self, time_step, trip_points):
        temp = self.midnight_early
        this_ptr = 0
        toreturn = []
        while temp < self.midnight_late:
            toreturn.append([temp, trip_points[this_ptr]])

            temp = temp + time_step

            this_ptr += 1
            if this_ptr >= len(trip_points):
                this_ptr = 0

        return toreturn
