__VERSION__ = "0.6.0.7"
# ruff: noqa: RUF100, UP025, UP004, I001, F401, E722
# -*- coding: utf-8 -*-
try:
    import uasyncio as asyncio
except:
    import asyncio
import time, json, gc, sys, machine
from uart_thread import UARTthread
from uart_link import UARTLink

class UARTHelpersClient (UARTthread):
    ################# INITIALIZATION AND DESTRUCTION #################
    def __init__(self, logger, cnf, tc):
        try:
            self._log.debug ({'msg': f'$p${__VERSION__}$p$ $a${self._txt_construct} {self._txt_launch}$a$', 'cls': __class__, 'acc': self._tc.waiting})
            self._link = UARTLink(self._my_info, False, cnf, lambda message: self._uart.send_line(message),
                                  self.__push_event, self._link_changed)
            super().__init__(logger, cnf, tc)
            self._uart._push_event = self.__push_event
            self._log.debug ({'msg': f'$p${__VERSION__}$p$ $a${self._txt_construct} {self._txt_finish}$a$', 'cls': __class__, 'acc': self._tc.success})
        except (Exception):
            self._log.critical ({'msg': f'$p${__VERSION__}$p$ {self._txt_construct} {self._txt_failed}', 'cls': __class__})
            raise
        finally:
            gc.collect()

    def destructor (self):
        try:
            self._log.debug ({'msg': f'$p${__VERSION__}$p$ $a${self._txt_destruct} {self._txt_launch}$a$', 'cls': __class__, 'acc': self._tc.waiting})
            super().destructor()
        finally:
            self._log.debug ({'msg': f'$p${__VERSION__}$p$ $a${self._txt_destruct} {self._txt_finish}$a$', 'cls': __class__, 'acc': self._tc.success})
            gc.collect()

    # Function to synchronise time between server and client
    def _sync_rtc(self, message=None):
        if message is None:
            self.read_line()
            return 0 if self._time_synchronised else None
        try:
            stamp = message['cmd']['data']['sv_ts']
            if type(stamp) not in (int, float):
                raise ValueError('invalid server timestamp')
            tm = time.localtime(stamp)
            machine.RTC().datetime((tm[0], tm[1], tm[2], tm[6], tm[3], tm[4], tm[5], 0))
            reply = {'rsp': {'act': 'sync', 'sta': 'ok',
                             'data': {'cl_ts': time.time(), 'sv_ts': int(stamp)}}}
            if not self.send_line(reply):
                self._log.warning({'msg': 'RTC reply could not be queued'})
                return None
            self._time_synchronised = True
            self._log.info({'msg': f'RTC synchronized with {self._dvc_name}'})
            return 0
        except (KeyError, TypeError, ValueError, OverflowError) as ex:
            self._log.warning({'msg': f'Invalid UART clock request: {ex}'})
            return None

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
