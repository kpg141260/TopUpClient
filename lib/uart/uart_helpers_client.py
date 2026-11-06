__VERSION__ = "0.6.0.8"
# ruff: noqa: RUF100, UP025, UP004, I001, F401, E722, BLE001, S110
# -*- coding: utf-8 -*-
try:
    import uasyncio as asyncio
except:
    import asyncio
import time, json, gc, sys, machine
from uart_thread import UARTthread
from uart_link import UARTLink
from uart_rtc import UARTClockSync

class UARTHelpersClient (UARTthread):
    ################# INITIALIZATION AND DESTRUCTION #################
    def __init__(self, logger, cnf, tc):
        try:
            self._log.debug ({'msg': f'$p${__VERSION__}$p$ $a${self._txt_construct} {self._txt_launch}$a$', 'cls': __class__, 'acc': self._tc.waiting})
            self._link = UARTLink(self._my_info, False, cnf, lambda message: self._uart.send_line(message),
                                  self.__push_event, self._link_changed)
            super().__init__(logger, cnf, tc)
            self._rtc = UARTClockSync(False, self.send_line, self._log, self._link.timeout_ms, self._set_rtc)
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

    def _set_rtc(self, stamp_ms):
        stamp = (stamp_ms + 500) // 1000
        tm = time.gmtime(stamp)
        machine.RTC().datetime((tm[0], tm[1], tm[2], tm[6], tm[3], tm[4], tm[5], 0))

    def _sync_rtc(self, message=None):
        if message is not None:
            self._rtc.receive(message)
        self._rtc.poll()
        self._time_synchronised = self._rtc.synced
        return 0 if self._rtc.synced else None

    # Push event to event buffer
    def __push_event (self, event: dict):
        if self._ev_buffer is None: return
        self._ev_buffer.put (event)

    def event_simulation (self, ev_buf_size: int):
        self._log.aprint (f'{self._tc.waiting}Starting UART event simulation...{self._tc.end}')
        for i in range (ev_buf_size):
            level = min((i + 1) * 10, 70) 
            self.__push_event ({'msg': f'This is a simulated event $p$[{i}]$p$', 'lvl': level, 'src': __name__})
            time.sleep (0.5)
