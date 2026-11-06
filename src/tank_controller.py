__VERSION__ = "0.6.0.6"
# ruff: noqa: RUF100, UP025, UP004, I001, F401, E722, BLE001
# -*- coding: utf-8 -*-
import  gc, time, json, sys # type: ignore
from    machine import Pin # type: ignore
from    devices import Relay, TempSensor
try:
    import uasyncio as asyncio # type: ignore
except:
    import asyncio

elapsed_refill_percent: float = 0.0

class TankController:
    def __init__(self, 
                logger,
                file_io,
                cnf_fn: str, 
                tc,
                state: dict,
                help_fcnts):
        logger.debug ({'msg': f'Version: $p${__VERSION__}$p$ $a$constructor launched...$a$', 'cls': __class__, 'acc': tc.waiting})
        self._tc               = tc
        self._cnf: dict        = {}
        self._log              = logger
        self._helpers          = help_fcnts
        self._tank_state: dict = state['tank']
        self._tmp_state:  dict = state['tmp']
        self._dvcs_state: dict = state['dvcs']
        self._measuring: bool  = False
        self._txt_refill       = 'refill'
        self._txt_reservoir    = 'Reservoir'
        self._txt_time         = 'time'
        self._txt_measure      = 'measurement'
        self._txt_elapsed      = 'Elapsed'
        self._txt_temp         = 'Temperature'
        self._txt_finished     = 'finished'
        self._txt_started      = 'started'
        self._unit_map         = {'C': 'Celsius', 'F': 'Fahrenheit', 'K': 'Kelvin'}
        try:
            # Open tank_controller configuration file
            self._cnf = file_io.load_json (cnf_fn)
            # Load default config
            self._sensor_errors: bool       = bool  (self._cnf['tank_cnf']['detect_sensor_errors'])
            self._use_refill: bool          = bool  (self._cnf['tank_cnf']['use_refill'])          
            self._refill_max_time: int      = int   (self._cnf['tank_cnf']['refill_max_time']) 
            self._min_cnt: int              = int   (self._cnf['ds18x20']['min_count'])
            self._text_encoding: str        = str   (self._cnf['text_encoding'])
            self._t_unit: str               = str   (self._cnf['temp_unit_char'])
            self._t_target: float           = float (self._cnf['tank_cnf']['t_target'])
            self._t_min: float              = float (self._cnf['tank_cnf']['t_min'])
            self._t_max: float              = float (self._cnf['tank_cnf']['t_max'])
            self._t_hyst_gap: float         = float (self._cnf['tank_cnf']['t_hyst_gap'])
            self._t_trend_slope_max: float  = float (self._cnf['tank_cnf']['t_trend_slope_max'])
            self._t_trend_min: float        = float (self._cnf['tank_cnf']['t_trend_min'])
            self._t_trend_max: float        = float (self._cnf['tank_cnf']['t_trend_max'])
            self._log.debug ({'msg': f'Target temp: $p${self._t_target}$p$, Min temp: $p${self._t_min}$p$, Max temp $p${self._t_max}$p$ Temp hysteresis: $p${self._t_hyst_gap}$p$, Max Refill time: $p${self._refill_max_time}$p$'})
            # Create relays and sensors
            self.pin_pump_sensor = Pin (self._cnf['sensors']['pump']['pin'],     mode = Pin.IN,  pull = self._cnf['sensors']['pump']['pull'])       # Yellow
            self.pin_resv_top    = Pin (self._cnf['sensors']['resv_top']['pin'], mode = Pin.IN,  pull = self._cnf['sensors']['resv_top']['pull'])   # Yellow
            self.pin_sump_low    = Pin (self._cnf['sensors']['resv_low']['pin'], mode = Pin.IN , pull = self._cnf['sensors']['resv_low']['pull'])   # Purple
            self.pin_resv_low    = Pin (self._cnf['sensors']['sump']['pin'],     mode = Pin.IN , pull = self._cnf['sensors']['sump']['pull'])       # Orange
            # Initialise Relays
            self.relays = {}
            self.relay_v     = Relay (self._cnf['relays']['valve'],   name='valve',   logger=logger, tc=self._tc, enabled=self._cnf['relays']['valve']['enabled'])
            self.relay_p     = Relay (self._cnf['relays']['pump'],    name='pump',    logger=logger, tc=self._tc, enabled=self._cnf['relays']['valve']['enabled'])
            self.relay_c     = Relay (self._cnf['relays']['chiller'], name='chiller', logger=logger, tc=self._tc, enabled=self._cnf['relays']['valve']['enabled'])
            self.relays.setdefault ('valve',   self.relay_v)
            self.relays.setdefault ('pump',    self.relay_p)
            self.relays.setdefault ('chiller', self.relay_c)
            self.temp_sensor = TempSensor (config=self._cnf['ds18x20'], logger=logger, tc=self._tc, enabled=self._cnf['ds18x20']['enabled'])
            self._cnf.clear()
            self._cnf = None
        finally:
            self._log.debug ({'msg': f'Version: $p${__VERSION__}$p$ $a$constructor {self._txt_finished}$a$', 'cls': __class__, 'acc': self._tc.success})
            gc.collect   ()
    # Class destructor
    def destructor (self) -> bool:
        """
            Class destructor to clean up objects and free up memory.
        """
        try:
            self._log.debug ({'msg': f'Version: $p${__VERSION__}$p$ $a$destructor {self._txt_started}...$a$', 'cls': __class__, 'acc': self._tc.waiting})
            # Make sure relay are OFF
            self.relay_p.destructor()
            self.relay_v.destructor()
            self.relay_c.destructor()
            self.temp_sensor.destructor()
            self._unit_map.clear()
            self._unit_map = None
            self.relay_v = None
            self.relay_p = None
            self.relay_c = None
            self.pin_pump_sensor = None
            self.pin_resv_top = None
            self.pin_sump_low = None
            self.pin_resv_low = None
            self.temp_sensor = None
            self._txt_refill = None
            self._txt_reservoir = None
            self._txt_time = None
            self._txt_measure = None
            self._txt_elapsed = None
            self._txt_temp = None
            self._txt_finished = None
            self._txt_started = None
            return True
        except Exception as ex:
            self._log.error ({'msg': f'{ex}', 'src': __name__, 'cls': __class__, 'fnc': __name__})
        finally:
            self._log.debug ({'msg': f'Version: $p${__VERSION__}$p$ $a$destructor finished$a$', 'cls': __class__, 'acc': self._tc.success})
            gc.collect()
    def __version__ (self):
        return __VERSION__
    def __repr__ (self):
        return f'{self.__class__} Ver.: {__VERSION__}'
    def __str__ (self):
        return f'{self.__class__}'

    ##### Manage chiller ##########################################################################
    # Check if chiller should be switched on or off
    ################################################################################################
    def check_temperature (self):
        try:
            temp, slope, trend, elapsed, n, fc_temp, self._fc_period = self.temp_sensor.get_trend()
            self._tmp_state['tank']      = temp
            self._tmp_state['slope']     = slope
            self._tmp_state['trend']     = trend
            self._tmp_state['elapsed']   = elapsed
            self._tmp_state['cnt']       = n
            self._tmp_state['fc_temp']   = fc_temp
            self._tmp_state['fc_period'] = self._fc_period
            if not self.relay_c.is_blocked(): # TODO: have another look at how to integrate the trend as a trigger
                if not self.relay_c.is_on():
                    if (temp > self._t_target or trend >= self._t_trend_max) or temp > (self._t_target + self._t_hyst_gap):
                        # switch chiller relay ON
                        self._dvcs_state['chiller'] = self.relay_c.on (enable_timer=True)
                else:        
                    if (temp < self._t_target or trend <= self._t_trend_min) or temp < (self._t_target - self._t_hyst_gap):
                        # switch chiller relay OFF
                        self._dvcs_state['chiller'] = self.relay_c.off (enable_timer=True)
        except Exception:
            self._tmp_state['tank']    = 0.0
            self._tmp_state['slope']   = 0.0
            self._tmp_state['trend']   = 0.0
            self._tmp_state['fc_temp'] = 0.0
            self._tmp_state['elapsed'] = 0
            self._tmp_state['cnt']     = 0
            raise
    # Main method to check tank status
    def check_tank (self):
        _func_name = 'check_tank'
        # Process temperature readings first
        try:
            self._dvcs_state['pump']      = 'ON'    if self.relay_p.is_on()          else 'OFF'
            self._dvcs_state['valve']     = 'ON'    if self.relay_v.is_on()          else 'OFF'
            self._dvcs_state['chiller']   = 'ON'    if self.relay_c.is_on()          else 'OFF'
            self._tank_state['rtop']      = "LOW"   if self.pin_resv_top.value()     else "FULL"
            self._tank_state['rbot']      = "EMPTY" if not self.pin_resv_low.value() else "FULL"
            self._tank_state['sump']      = "LOW"   if self.pin_sump_low.value()     else "FULL"
            self._tank_state['reservoir'] = "FULL"  if self.pin_resv_low.value() and not self.pin_resv_top.value() else "LOW"
        except NotImplementedError as ex:
            self._log.warning ({'msg': ex})
        except KeyError:
            raise
        try:
            ##### Manage water TankController for reservoir tank ####################################################
            # Check if top reservoir sensor is high (indicating reservoir is below top level) and
            # if valve relay is switched off
            ################################################################################################
            if not self.relay_v.is_blocked() and not self._measuring:
                if self.pin_resv_top.value() and not self.relay_v.is_on():
                    # switch valve relay ON to top up water in reservoir
                    self._dvcs_state['valve'] = self.relay_v.on (enable_timer=True)

                # Check if top reservoir sensor is low (indicating reservoir is full) and
                # if valve relay is switched on
                if not self.pin_resv_top.value() and self.relay_v.is_on() and not self._measuring:
                    # block_v = True
                    self._dvcs_state['valve'] = self.relay_v.off (enable_timer=True)
                
            # Check if bottom reservoir sensor is low (indicating reservoir is empty) and
            # if pump relay is ON         
            if not self.pin_resv_low.value() and self.relay_p.is_on() and not self.relay_p.block and not self._measuring:
                # switch pump relay OFF
                self._log.info ({'msg': f'{self._txt_reservoir} $a$EMPTY$a$, switching tank pump $a$OFF$a$.', 'src': __name__, 'fnc': _func_name, 'acc': self._tc.bred})
                self._dvcs_state['pump'] = self.relay_p.off (enable_timer=True)

            ##### Manage sump/tank water level ##################################################################
            # Check if SUMP tank sensor is LOW meaning the sump is LOW and 
            # that the relay block is not on preventing relay flutter
            # and that the relay is actually switched off
            ################################################################################################
            if not self.relay_p.is_blocked() and not self._measuring:
                if not self.pin_sump_low.value() and self.relay_p.is_on():
                    self._dvcs_state['pump'] = self.relay_p.off (enable_timer=True)

                if self.pin_sump_low.value() and not self.relay_p.is_on() and self.pin_resv_low.value():
                # Check if sump sensor is low meaning the sump is not full and 
                # that the relay block is not on preventing relay flutter
                # and that the pump relay is off
                # This scenario will occur after the reservoir was empty and reservoir control
                # switched off the pump
                    self._dvcs_state['pump'] = self.relay_p.on (enable_timer=True)

            ##########################################################################
            # Possible error conditions:
            # Lower sensor shows reservoir empty and top sensor shows reservoir full
            ##########################################################################
            if not self.pin_resv_low.value() and self.pin_resv_top.value() and self._sensor_errors:
                self._log.error ({'msg': f'Inconsistent sensor reading: $p${self._txt_reservoir} bottom$p$ $a$EMPTY$a$ and $p${self._txt_reservoir} top$p$ $a$FULL$a$!', 'cls': __class__, 'src': __name__, 'fnc': _func_name, 'acc': self._tc.bred})
                raise RuntimeError (f'Inconsistent sensor reading: {self._txt_reservoir} bottom $a$EMPTY$a$ and {self._txt_reservoir} top $a$FULL$a$!')
        except NotImplementedError as ex:
            self._log.warning ({'msg': ex})
        except RuntimeError:
            raise
    # Function to measure the time it takes to refill the reservoir
    async def as_msr_rfl (self, name: str, task_info: dict):
        try:
            self._measuring = True
            elapsed  = 0
            interval = task_info.get('interval', 60) # default to 60 seconds
            duration = task_info['duration'] * interval # duration in seconds
            start = time.time () #type: ignore

            self._dvcs_state['valve'] = self.relay_v.on()
            self._dvcs_state['pump']  = self.relay_p.off()
            self._log.debug ({'msg': f'$f${name}$f$ $i${task_info['task_id']}$i$ $a$has started$a$', 'acc': self._tc.success})
            self._log.info ({'msg': f'$a${self._txt_reservoir} {self._txt_refill} {self._txt_started}, Interval:$a$ $p${interval} sec$p$ $a$Duration:$a$ $p${duration} sec$p$$a$...$a$', 'acc': self._tc.waiting})

            # Loop until the top reservoir valve shows full (0)
            while True:
                now = time.time () #type: ignore
                elapsed = now - start
                percent = round ((elapsed / duration) * 100, 2)
                if elapsed > 0:
                    self._log.info ({'msg': f'{self._txt_reservoir} {self._txt_refill} -> $p${self._txt_elapsed}:$p$ $a${percent}% \t{self._helpers.sec_to_hms(int (elapsed))}$a$', 'acc': self._tc.success})
                if elapsed >= duration or not self.pin_resv_top.value():
                    self._log.info ({'msg': f'{self._txt_reservoir} {self._txt_refill} time: $a${self._helpers.sec_to_hms(int (elapsed))}$a$', 'acc': self._tc.success})
                    self._dvcs_state['valve'] = self.relay_v.off() # Make sure to switch OFF the valve
                    self._refill_max_time = elapsed
                    self._measuring = False
                    break
                await asyncio.sleep (interval)
        except NotImplementedError as ex:
            self._log.warning ({'msg': ex})
        except KeyError as ex:
            raise KeyError (f'[{type (ex)}]: {ex!s} - not found in task_info')
        except asyncio.CancelledError:
            self._log.debug ({'msg': f'$f${name}$f$ $i${task_info['task_id']}$i$$a$ cancelled$a$', 'src': __name__})
            self._dvcs_state['valve'] = self.relay_v.off() # Make sure to switch OFF the valve
            self._measuring = False
            raise
        except Exception as ex:
            raise RuntimeError (f'[{type(ex)}]: {ex!s}')
    # Set the temperature unit of on-board and tank sensor
    def set_temp_unit (self, unit: str):
        self._t_unit = unit
        self.temp_sensor.temp_unit (self._t_unit)
    # Display the current temperature trend
    def print_trend (self):
        try:
            temp, slope, trend, elapsed, cnt, fc_temp, fc_period = self.temp_sensor.get_trend ()
        except NotImplementedError as ex:
            self._log.warning ({'msg': ex})
        else:
            if cnt > self._min_cnt:
                if slope < -0.01:
                    txt_slope = 'decreased by '
                    txt_trend = 'decrease per minute'
                    c = self._tc.cyan
                elif slope >= -0.01 and slope <= 0.01:
                    txt_slope = 'remained at '
                    txt_trend = '- not changed'
                    c = self._tc.green
                else:
                    txt_slope = 'increased by '
                    txt_trend = 'increase per minute'
                    c = self._tc.red
                if temp > self._t_target and slope != 0:
                    run_time = round (abs((temp - self._t_target) / slope), 2)
                else:
                    run_time = 0.0
                self._log.aprint (f'{self._tc.info}Current tank {self._txt_temp}: {self._tc.par}{temp:+.2f}{self._t_unit}\n' +
                        f'{self._tc.info}Current tank {self._txt_temp} trend: {c}{slope:+.2f}{self._t_unit} {txt_trend}\n' +
                        f'{self._tc.info}Tank {self._txt_temp} has {c}{txt_slope}{trend:+.2f}{self._t_unit} {self._tc.info}over a period of {self._tc.par}{elapsed:.2f} min{self._tc.end}\n' +
                        f'{self._tc.info}Projected tank {self._txt_temp} in {self._tc.par}{fc_period:.2f} min {self._tc.info} will be {c}{fc_temp:+.2f}{self._t_unit}{self._tc.end}\n' +
                        f'{self._tc.info}Projected remaining chiller runtime: {self._tc.par}{run_time:.2f} min{self._tc.end}\n')
            else:
                self._log.aprint (f'{self._tc.info}Not enough data yet: {self._tc.par}{cnt} samples{self._tc.end}')
    # Read the current temperature from the tank sensor
    def read_temp (self) -> float:
        t: float = 0.0
        try:
            t = float (self.temp_sensor.read_temp())
        except Exception as ex:
            sys.print_exception (ex)
            raise
        else:
            return float (t) # Return the temperature as a float
    # Convert temperature from one unit to another
    # Supported units: C (Celsius), F (Fahrenheit), K (Kelvin
    def convert_temperature (self, value, from_unit, to_unit):
        from_unit = from_unit.upper()
        to_unit   = to_unit.upper()

        # Normalize to Celsius first
        if from_unit == 'F':
            value = (value - 32) * 5 / 9
        elif from_unit == 'K':
            value = value - 273.15
        elif from_unit != 'C':
            raise ValueError("Unsupported from_unit")

        # Convert from Celsius to target
        if to_unit == 'F':
            return value * 9 / 5 + 32
        elif to_unit == 'K':
            return value + 273.15
        elif to_unit == 'C':
            return value
        else:
            raise ValueError("Unsupported to_unit")
    # Switching function for relay ON
    def switch (self, device=None, action=None):
        if device and action:
            # Get the parameter for the required action (on/off)
            fnc = f'{action.lower()}'
            # Check if the 
            if hasattr(self.relays[device], fnc):
                hdlr = getattr(self.relays[device], fnc)
                hdlr()
        else:
            raise NotImplementedError (f'Device: {self._tc.par}{device}{self._tc.end} not defined!')
    def print_tank_state (self):
        max_len_d = max (len (key) for key in self.state['dvcs'])
        max_len_t = max (len (key) for key in self.state['tank'])
        max_len = max (max_len_d, max_len_t)
        self._log.aprint (f'\n{self._tc.ul}{self._tc.dvc}Devices State{self._tc.end}')
        for key in sorted(self.state['dvcs'].keys()):
            self._log.aprint (f'{self._tc.cyan}{key}:<{max_len}\t{self._tc.par}{self.state['dvcs'][key]}{self._tc.end}')

        self._log.aprint (f'\n{self._tc.ul}{self._tc.dvc}Tank State{self._tc.end}')
        for key in sorted(self.state['tank'].keys()):
            self._log.aprint (f'{self._tc.cyan}{key}:<{max_len}\t{self._tc.par}{self.state['tank'][key]}{self._tc.end}')

########## Class properties ##########
    @property
    def max_refill_time (self)  -> int:
        return self._refill_max_time
    @max_refill_time.setter
    def max_refill_time (self, value: int):
        self._refill_max_time = value
    @property
    def get_elapsed_refill_time (self)  -> float:
        global elapsed_refill_percent
        return elapsed_refill_percent
    @property
    def temp_unit (self):
        return self._t_unit
    @temp_unit.setter
    def temp_unit (self, value: str):
        if value.upper() == self._t_unit:
            return
        from_unit = self._t_unit
        to_unit   = value.upper() 
        self._t_unit = value.upper()
        self.temp_sensor.temp_unit (self._t_unit)
        # Convert temperature hysteresis width only if unit is C to F or F to C - the width remains the same if Kelvin
        if (from_unit == 'F' and to_unit == 'C') or (from_unit == 'C' and to_unit == 'F'):
            self._t_hyst_gap = self.convert_temperature (self._t_hyst_gap, from_unit, to_unit)
        self._t_min             = self.convert_temperature (self._t_min, from_unit, to_unit)
        self._t_max             = self.convert_temperature (self._t_max, from_unit, to_unit)
        self._t_target          = self.convert_temperature (self._t_target, from_unit, to_unit)
        self._t_trend_slope_max = self.convert_temperature (self._t_trend_slope_max, from_unit, to_unit)
        self._log.info ({'msg': f'{self._txt_temp} unit changed from $p${self._unit_map.get(from_unit)}$p$ to $p${self._unit_map.get(to_unit)}$p$', 'src': __name__, 'fnc': 'temp_unit'})
    @property
    def target_temp (self) -> float:
        return self._t_target
    @target_temp.setter
    def target_temp (self, value):
        try:
            self._t_target = float (value)
        except:
            raise ValueError (f'Exception setting target temperature: {value}')
    @property
    def temp_hysteresis_width (self) -> float:
        return self._t_trend_slope_max
    @temp_hysteresis_width.setter
    def temp_hysteresis_width (self, value):
        try:
            self._t_trend_slope_max = float (value)
        except:
            raise ValueError (f'Exception setting hysteresis width: {value}')
    @property
    def temp_max (self):
        return self._t_max
    @temp_max.setter
    def temp_max (self, value):
        try:
            self._t_max = float (value)
        except:
            raise ValueError (f'Exception setting max temperature: {value}')
    @property
    def temp_min (self):
        return self._t_min
    @temp_min.setter
    def temp_min (self, value):
        try:
            self._t_min = float (value)
        except:
            raise ValueError (f'Exception setting min temperature: {value}')
