__VERSION__ = "0.6.0.1"
# ruff: noqa: RUF100, UP025, UP004, I001, F401, BLE001, S110
# -*- coding: utf-8 -*-
import gc, time 
from   machine     import ADC 
from   collections import deque

class FixedSizeFIFO:
    def __init__(self, size, name: str = ''):
        """
        Initialize the FixedSizeFIFO object.

        Parameters
        ----------
        size : int
            The maximum number of items to store in the queue.
        """
        self._size: int = size
        self.queue      = deque((), size)  # Fixed-size buffer
        self._name: str = name

    def __iter__(self):
        """Return an iterator over the queue elements."""
        return iter(self.queue)

    def __len__(self):
        """Return the number of items in the queue."""
        return len(self.queue)

    def __str__(self):
        return self._name

    def put (self, item):
        """
        Add an item to the queue. Removes oldest if full.

        Parameters
        ----------
        item
            The item to add to the queue.
        """
        if len(self.queue) >= int (self._size):
            self.queue.popleft()  # Remove the oldest item

        self.queue.append(item)  # Add new item

    def get(self):
        """
        Get the oldest item from the queue or None if empty.

        Returns
        -------
        item or None
        """
        return self.queue.popleft() if self.queue else None

    def clear(self):
        """Clear all items from the queue."""
        self.queue = deque((), self._size)  # Reinitialize

    def size (self) -> int:
        """Return the number of items in the queue."""
        return len(self.queue)

    def space (self) -> int:
        """Return the remaining space in the queue."""
        return int (self._size) - len(self.queue)

class helpers:
    tc = None
    def __init__ (self, adc_pin = 4, tc=None):
        self._adc_pin     = adc_pin
        self._temp_sensor = ADC (self._adc_pin)
        helpers.tc = tc

    def __destruct__ (self):
        del self._temp_sensor

    # Internal temperature sensor is connected to ADC channel 4
    def get_core_temp ( self ) -> float:
        # Temperature calculation based on sensor characteristics
        return (27 - (self._temp_sensor.read_u16() * 0.001 / 340))

    @classmethod
    def get_mem_info (cls, percent: bool=False):
        f  = f'{helpers.tc.info}Free memory     :{helpers.tc.end}' 
        a  = f'{helpers.tc.info}Allocated memory:{helpers.tc.end}' 
        fm = gc.mem_free() 
        am = gc.mem_alloc() 
        if not percent:
            return f'{f} {helpers.tc.info}{fm}\n{a} {helpers.tc.error}{am}{helpers.tc.end}' 
        else:
            fmp = fm/(fm+am) * 100
            amp = am/(fm+am) * 100

            if fmp < 25.0:
                fmc = helpers.tc.critical 
            elif fmp < 45.0:
                fmc = helpers.tc.warning 
            else:
                fmc = helpers.tc.success 
            if amp < 50.0:
                amc = helpers.tc.success 
            elif amp < 65.0:
                amc = helpers.tc.warning 
            else:
                amc = helpers.tc.error 

            free = f"{fmp:2.2f}"  
            aloc = f"{amp:2.2f}"  

            return (f'{f} {fmc}{fm:06d} bytes - {free}%{helpers.tc.end}\n{a} {amc}{am:06d} bytes - {aloc}%{helpers.tc.end}') 

    @staticmethod
    def sec_to_hms ( s ):
        h, r = divmod (s, 3600)
        m, s = divmod (r, 60)
        hr = f'{h:0>2} hr ' if h > 0 else ''
        return f'{hr}{m:0>2} min {s:0>2} sec'

    @staticmethod
    def seconds_to_dhms ( seconds: int, format:bool = True ):
        # Convert seconds into days, hours, minutes and seconds
        days    = seconds // 86400
        hours   = (seconds % 86400) // 3600
        minutes = (seconds % 3600) // 60
        seconds = seconds % 60

        if format:
            return f"{days}:{hours:02d}:{minutes:02d}:{seconds:02d}"
        else:
            return days, hours, minutes, seconds

    @staticmethod
    def get_time_stamp (format: str | None=None, prefix='') -> str:
        if format is None:
            return

        tm = time.gmtime()

        format_map = {
            "%Y": f"{tm[0]:04d}", # Year
            "%m": f"{tm[1]:02d}", # Month
            "%d": f"{tm[2]:02d}", # Day
            "%H": f"{tm[3]:02d}", # Hour
            "%M": f"{tm[4]:02d}", # Minute
            "%S": f"{tm[5]:02d}", # Second
        }

        for key, value in format_map.items():
            format = format.replace (key, value)

        return prefix + format
