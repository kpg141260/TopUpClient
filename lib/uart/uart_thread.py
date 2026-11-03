__VERSION__ = "0.6.0.4"
# ruff: noqa: RUF100, UP025, UP004, I001, F401, BLE001
# -*- coding: utf-8 -*-
import  gc, time
import  json
from    logger.logger    import dbg_lvls as dl 
from    uart_full_duplex import FullDuplexUART
from    shared_core      import shared, state_lock, report_progress

class UARTthread:

    def __init__  (self, logger, cnf, tc):
        try:
            self._tc = tc
            self._me = 'Core 1 UART thread'
            self._log.debug (f'{self._me} {self._txt_construct} {self._txt_launch}')
            super().__init__()
            self._time_synchronised    = False
            self._uart = FullDuplexUART (logger, cnf, tc=tc)
            self._log.debug (f'{self._me} {self._txt_construct} {self._txt_finish}')
        except (Exception):
            self._log.critical (f'{self._me} {self._txt_construct} {self._txt_failed}')
            raise
        finally:
            gc.collect ()

    def __destruct__ (self):
        try:
            self._log.debug (f'{self._me} {self._txt_destruct} {self._txt_launch}')
            self._uart.__destruct__ ()
        finally:
            self._log.debug (f'{self._me} {self._txt_destruct} {self._txt_finish}')
            gc.collect()

    @property
    def can_send (self):
        return self._uart.can_send

    def __main_thread ( self) -> None:
        ########### repetitive loop to receive and transmit data ###########
        try:
            self.__push_event ({'msg': f'$v${self._me}$v$ $a$active$a$', 'lvl': dl.INFO, 'acc': self._tc.success})
            while True:
                try:
                    with state_lock:
                        stopping = shared['stop']
                        paused = shared['pause']
                    if stopping:
                        # clean shutdown
                        self._uart.clear_buffers ()
                        # Send exit command to server
                        self._uart.send_line ({'cmd': {'act': 'exit'}})
                        self._uart._write ()
                        # Wait for server to digest exit command
                        time.sleep (self._thread_interval)
                        # Exit thread
                        return
                    elif not paused:
                        # Read data from UART
                        self._uart._read ()
                        # Wait before sending data
                        time.sleep (self._thread_interval)
                        # Check if data can be send (CTS low)
                        if self._uart.can_send:
                            # Transmit data
                            self._uart._write ()
                        # Wait before next cycle
                    time.sleep (self._thread_interval)
                    report_progress()
                except (Exception) as ex:
                    report_progress(error=ex)
                    self.__push_event ({'msg': f'{self._me} - exception transmitting data -> {ex}, mem free: {gc.mem_free()}', 'lvl': dl.ERROR})
                time.sleep(self._thread_interval)
        finally:
            with state_lock:
                shared['stop'] = False
                shared['hb'] = 0
                shared['state'] = 'stopped'
            self.__push_event ({'msg': f'$v${self._me}$v$ $a$terminated$a$', 'lvl': dl.INFO, 'acc': self._tc.success})
            gc.collect ()
