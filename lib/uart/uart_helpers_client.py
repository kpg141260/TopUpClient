__VERSION__ = "0.6.0.6"
# ruff: noqa: RUF100, UP025, UP004, I001, F401, E722
# -*- coding: utf-8 -*-
try:
    import uasyncio as asyncio
except:
    import asyncio
import time, json, gc, sys, machine
from uart_thread import UARTthread

class UARTHelpersClient (UARTthread):
    ################# INITIALIZATION AND DESTRUCTION #################
    def __init__(self, logger, cnf, tc):
        try:
            self._log.debug ({'msg': f'$p${__VERSION__}$p$ $a${self._txt_construct} {self._txt_launch}$a$', 'cls': __class__, 'acc': self._tc.waiting})
            super().__init__(logger, cnf, tc)
            self._log.debug ({'msg': f'$p${__VERSION__}$p$ $a${self._txt_construct} {self._txt_finish}$a$', 'cls': __class__, 'acc': self._tc.success})
        except (Exception) as ex:
            self._log.critical ({'msg': f'$p${__VERSION__}$p$ {self._txt_construct} {self._txt_failed}', 'cls': __class__})
            raise
        finally:
            gc.collect()

    def __destruct__ (self):
        try:
            self._log.debug ({'msg': f'$p${__VERSION__}$p$ $a${self._txt_destruct} {self._txt_launch}$a$', 'cls': __class__, 'acc': self._tc.waiting})
            super().__destruct__()
        finally:
            self._log.debug ({'msg': f'$p${__VERSION__}$p$ $a${self._txt_destruct} {self._txt_finish}$a$', 'cls': __class__, 'acc': self._tc.success})
            gc.collect()

    # Function to synchronise time between server and client
    def _sync_rtc  (self):
        # This code is only launched by the main thread after the server has synchronised its own RTC with a NTP server.
        _rtc = machine.RTC()
        try:
            cmd = self._uart.read_line ()
            if not cmd:
                return
            print (f'{self._tc.info}Received: {self._tc.par}{cmd}{self._tc.end}')
            if b'sync' in cmd:
                _data = json.loads (cmd.decode(self._encoding).replace('\n', ''))
                self._log.info ({'msg': f'{self._txt_rtc_sync}: $p${_data}$p$'})
                # Server has sent timestamp, convert to time tuple (year, month, mday, hour, minute, second, weekday, yearday)
                tm = time.localtime (_data['cmd']['data']['sv_ts'])
                tm1 = [tm[0], tm[1], tm[2], tm[6], tm[3], tm[4], tm[5], 0]
                # Set RTC with time tuple (year, month, day, weekday, hours, minutes, seconds, sub-seconds)
                _rtc.datetime (tm1)
                self._uart.send_line ({'rsp': {'act': 'sync', 'sta': 'ok', 'data': {'cl_ts': time.time(), 'sv_ts': int (_data['cmd']['data']['sv_ts'])}}})
                self._log.info ({'msg': f'{self._txt_rtc_sync} with $p${self._dvc_info}$p$ $a${self._txt_success} {self._txt_finish}$a$', 'acc': self._tc.success})
                self._time_synchronised = True
                del _data
        except UnicodeError as ex:
            self._log.error ({'msg': ex})
        except (ValueError, TypeError):
            raise
        finally:
            del cmd
            gc.collect()

    # Push event to event buffer
    def __push_event (self, event: dict):
        if self._ev_buffer is None: return
        event['ts'] = event.get('ts', self._log.get_time_stamp())
        self._ev_buffer.put (event)

    def event_simulation (self, ev_buf_size: int):
        self._log.aprint (f'{self._tc.waiting}Starting UART event simulation...{self._tc.end}')
        for i in range (ev_buf_size):
            level = min((i + 1) * 10, 70) 
            self.__push_event ({'msg': f'This is a simulated event $p$[{i}]$p$', 'lvl': level, 'src': __name__})
            time.sleep (0.5)
