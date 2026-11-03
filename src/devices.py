__VERSION__ = "0.6.0.4"
# ruff: noqa: RUF100, UP025, UP004, I001, F401
# -*- coding: utf-8 -*-
import onewire, ds18x20, time        # type: ignore
from   machine     import Pin, Timer # type: ignore
from   collections import deque

block_active = False

def isr_block (t):
    """
        This is an ISR (Interrupt Service Routine) that is triggered by a Timer.
        It deactivates the block by setting the global block_active flag to False.

        Parameters
        ----------
        t : Timer
            The Timer object that calls this ISR.

        Returns
        -------
        None
    """
    global block_active
    block_active = False

class Relay:
    class State:
        ON = True
        OFF = False

    def __init__(self, config: dict, logger, name: str, tc, enabled) -> None:
        self._name = name
        self._log = logger
        self._tc = tc
        self._timer = Timer(-1)
        self._enabled = enabled
        self._relay_status = Relay.State.OFF
        try:
            self._id = config['id']
            self._active_level = config['active_state']
            self._block_time = config['block_time']
            self._relay_pin = Pin(config['pin'], mode=Pin.OUT)
            if config['initial_state'] == Relay.State.OFF:
                self.off()
            else:
                self.on()
        except KeyError:
            raise KeyError(f'{self._tc.function}{__name__}.init{self._tc.end} -> Missing key in config dictionary.')
        self._log.info({'msg': f'Relay $p${self._name}$p$ initialized with ID $p${self._id}$p$, Pin: $p${self._relay_pin}$p$, Active level: $p${self._active_level}$p$, Block time $p${self._block_time} sec$p$'})

    def __destruct__(self):
        self.off()
        self._timer.deinit()

    def is_enabled(self):
        if not self._enabled:
            raise NotImplementedError(f'Relay {self._name} not available')
        return True

    def toggle(self, enable_timer: bool = False) -> bool:
        global block_active
        self.is_enabled()
        if not block_active:
            if enable_timer:
                self._timer.init(period=self._block_time, mode=Timer.ONE_SHOT, callback=isr_block)
                block_active = True
            self._relay_pin.toggle()
            self._relay_status = not self._relay_status
            self._log.info({'msg': f'Relay {self._name} toggled to {"ON" if self._relay_status else "OFF"}', 'acc': self._tc.success})
        return self._relay_status

    def on(self, enable_timer: bool = False, force: bool = False) -> bool:
        global block_active
        self.is_enabled()
        if force or not self._relay_status:
            if not block_active or force:
                if enable_timer and not force:
                    self._timer.init(period=self._block_time, mode=Timer.ONE_SHOT, callback=isr_block)
                    block_active = True
                if self._active_level:
                    self._relay_pin.on()
                else:
                    self._relay_pin.off()
                self._relay_status = Relay.State.ON
                self._log.info({'msg': f'Relay {self._name} switched ON', 'acc': self._tc.success})
        return self._relay_status

    def off(self, enable_timer: bool = False, force: bool = False) -> bool:
        global block_active
        self.is_enabled()
        if force or self._relay_status:
            if enable_timer and not force:
                self._timer.init(period=self._block_time, mode=Timer.ONE_SHOT, callback=isr_block)
                block_active = True
            if self._active_level:
                self._relay_pin.off()
            else:
                self._relay_pin.on()
            self._relay_status = Relay.State.OFF
            self._log.info({'msg': f'Relay {self._name} switched OFF', 'acc': self._tc.success})
        return self._relay_status

    def is_on(self) -> bool:
        self.is_enabled()
        return self._relay_status

    def block(self, enable: bool) -> bool:
        global block_active
        self.is_enabled()
        block_active = enable
        if block_active:
            self._timer.init(period=self._block_time, mode=Timer.ONE_SHOT, callback=isr_block)
        return block_active

    def is_blocked(self):
        self.is_enabled()
        return block_active

    @property
    def enabled(self):
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool):
        self._enabled = value
        
class TempSensor:
    def __init__(self, config: dict, logger, tc, enabled: bool, name='DS18X20'):
        self._tc = tc
        self._enabled = enabled
        self._name = name
        self._log = logger
        self._kelvin = config['kelvin']
        self._unit = config['unit']
        self._idx = config['index']
        self._min_len = config['min_count']
        self._max_len = config['max_count']
        self._fc_period = config['fc_period']
        self._temps = deque((), self._max_len)
        self._ds_pin = Pin(config['pin'])
        self._ds_sensor = None
        try:
            self._ds_sensor = ds18x20.DS18X20(onewire.OneWire(self._ds_pin))
            self.is_enabled()
            self._sensors = self._ds_sensor.scan()
        except NotImplementedError as ex:
            self._log.warning ({'msg': f'{str (ex)}'})
            return
        except Exception:
            raise
        self._cnt = len(self._sensors)
        self._ms = int(750 / (2 ** (12 - config['precision'])))
        # Set DS18X20 precision
        if config['precision'] == 9:
            self._prcsn = b'\x00\x00\x1f'
        elif config['precision'] == 10:
            self._prcsn = b'\x00\x00\x3f'
        elif config['precision'] == 11:
            self._prcsn = b'\x00\x00\x5f'
        elif config['precision'] == 12:
            self._prcsn = b'\x00\x00\x7f'
        else:
            raise ValueError(f'Invalid precision {config["precision"]}. Possible values: 9, 10, 11, 12')
        for sensor in self._sensors:
            self._ds_sensor.write_scratch(sensor, self._prcsn)
        if self._cnt >= 1 and self._idx < 0:
            raise IndexError(f'{self._cnt} DS18X20 found; Index max = {self._cnt - 1}; Index specified = {self._idx}.')
        else:
            self._idx = 0

    def __destruct__(self):
        if self._ds_sensor:
            del self._ds_sensor
        if self._sensors:
            del self._sensors
        del self._temps
        del self._ds_pin
        del self._tc
        del self._name
        del self._kelvin
        del self._unit
        del self._idx
        del self._min_len
        del self._max_len
        del self._fc_period
        del self._ms

    def __read(self) -> float:
        try:
            self.is_enabled()
            self._ds_sensor.convert_temp()
            time.sleep_ms(self._ms)
            return self._ds_sensor.read_temp(self._sensors[self._idx])
        except Exception as ex:
            raise ex

    def read_temp(self) -> float:
        try:
            now = time.time() / 60
            t = self.__read()
            if self._unit == 'F':
                t = t * (9 / 5) + 32
            elif self._unit == 'K':
                t = t + self._kelvin
            if len(self._temps) > self._max_len:
                self._temps.pop()
            self._temps.append((now, t))
            return round(t, 2)
        except Exception as ex:
            raise ex

    def select_device(self, index: int = 0):
        if self._cnt > 1:
            if index >= self._cnt or index < 0:
                raise IndexError(f'Index for DS18X20 {index} is out of bounds. Select 0 to {self._cnt - 1}')
        self._idx = index

    def get_trend(self):
        try:
            temp = self.read_temp()
            n = len(self._temps)
            if n < self._min_len:
                return [temp, 0.0, 0.0, 0.0, n, 0.0, self._fc_period]
            x = [t[0] for t in self._temps]
            y = [t[1] for t in self._temps]
            x_mean = sum(x) / n
            y_mean = sum(y) / n
            numerator = sum((x[i] - x_mean) * (y[i] - y_mean) for i in range(n))
            denominator = sum((x[i] - x_mean) ** 2 for i in range(n))
            if denominator == 0:
                return [temp, 0.0, 0.0, 0.0, n, 0.0, self._fc_period]
            slope = round(numerator / denominator, 2)
            elapsed = round(x[-1] - x[0], 2)
            trend = round(y[-1] - y[0], 2)
            projected_temp = round(temp + slope * self._fc_period, 2)
            return [temp, slope, trend, elapsed, n, projected_temp, self._fc_period]
        except Exception as ex:
            raise ex

    def temp_unit(self, unit: str):
        unit = unit.upper()
        if unit not in ['C', 'F', 'K']:
            raise ValueError('Temperature unit must be C, F, or K')
        self._unit = unit

    @property
    def enabled(self):
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool):
        self._enabled = value

    def is_enabled(self):
        if not self._enabled:
            raise NotImplementedError(f'Temperature sensor {self._name} not enabled')
        return True
    
class LiquidSensor:
    class state:
        HIGH: bool = True
        LOW:  bool = False
    
    class active_level:
        HIGH: bool = True
        LOW:  bool = False

    def __init__ (self, config: dict, tc, enable: bool):
        self._txt_not_avail = 'not available'
        self._txt_sensor    = 'Sensor'
        self._txt_type      = 'Liquid'
        self._tc            = tc
        self._name          = config['name']
        self.active_state   = config['active_state']
        self.pin            = Pin (config['pin'], mode=Pin.IN, pull=config['pull'])
        self._enabled       = enable
        
    def __del__ (self):
        del self._name
        del self.active_state
        del self.pin
        del self._txt_not_avail
        del self._txt_sensor
        del self._txt_type

    def is_enabled (self):
        if not self._enabled:
            raise NotImplementedError (f'{self._txt_type} {self._txt_sensor} {self._name} {self._txt_not_avail}')
        return True
        
    @property
    def enabled (self):
        return self._enabled
    @enabled.setter
    def enabled (self, value: bool):
        self._enabled = value

# TODO: continue with sensor code