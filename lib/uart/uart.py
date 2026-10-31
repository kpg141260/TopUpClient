__VERSION__ = "0.5.0.3"
# ruff: noqa: RUF100, UP025, UP004, I001, F401, BLE001, B012
# -*- coding: utf-8 -*-
import  gc
import  time
import  machine
import  json
import  _thread
from    machine             import Pin
from    ansi_esc            import text_colors as tc
from    uart_helpers_client import UARTHelpersClient
from    shared_core         import shared, state_lock
from    logger.logger       import Logger
from    logger.logger       import dbg_lvls as dl


class UARTComms (UARTHelpersClient):
########## INITIALIZATION AND DESTRUCTOR METHODS ##########
    def __init__(
            self,
            logger,
            file_io,
            cnf_fn: str,
            tc,
            name: str,
            event_buffer
        ):
        gc.collect()
        self._mem_start     = gc.mem_free ()
        self._txt_construct = 'constructor'
        self._txt_destruct  = 'destructor'
        self._txt_finish    = 'finished'
        self._txt_failed    = 'failed'
        self._txt_launch    = 'launched...'
        self._txt_rtc_sync  = 'RTC sync'
        self._txt_success   = 'successfully'
        self._cnf           = None

        try:
            self._log       = logger
            self._tc        = tc
            self._my_info   = name # name of the server/client
            self._dvc_name  = 'na' # name of the server/external device
            self._dvc_ver   = 'na' # version of the server/external device
            self._dvc_build = 'na' # build number of the server/external device
            self._ev_buffer = event_buffer
            self._log.debug ({'msg': f'$p${__VERSION__}$p$ $a${self._txt_construct} {self._txt_launch}$a$', 'cls': __class__, 'acc': self._tc.waiting})
            self._dvc_cnctd:       bool  = False # flag signalling whether the server device is connected
            self._thread_running:  bool  = False
            self._hs_active:       bool  = False
            self._hs_paused:       bool  = False
            self._sync_active:     bool  = False
            self._dvc_cnctd:       bool  = False
            self._cmd:             dict  = {}
            self._cnf:             dict  = file_io.load_json (cnf_fn)
            self._uart_buf_size:    int  = self._cnf['uart_buf_size']
            self._encoding:         str  = self._cnf['encoding']
            self._hs_rcv_delay:     int  = self._cnf.get('hs_rcv_delay', 0.5)
            self._uart_interval:  float  = self._cnf.get('uart_interval', 0.01)
            self._thread_interval: float = self._cnf.get('uart_thread_interval', 0.01)
            self._thread_paused:    bool = False
            self._challenge:        str  = self._cnf.get('challenge_phrase', 'ping')
            self._response:         str  = self._cnf.get('challenge_response', 'pong')
            super().__init__(logger, self._cnf, self._tc)
            self._log.debug ({'msg': f'$p${__VERSION__}$p$ $a${self._txt_construct} {self._txt_finish}$a$', 'cls': __class__, 'acc': self._tc.success})
        except Exception:
            self._log.critical ({'msg': f'$p${__VERSION__}$p$ {self._txt_construct} {self._txt_failed}', 'cls': __class__})
            raise
        finally:
            if self._cnf:
                # Clear comms configuration
                self._cnf.clear()
                del self._cnf
            gc.collect()

    def __destruct__ (self):
        try:
            self._log.debug ({'msg': f'$p${__VERSION__}$p$ $a${self._txt_destruct} {self._txt_launch}$a$', 'cls': __class__, 'acc': self._tc.waiting})
            super().__destruct__()
            self._dvc_cnctd = False
            del self._dvc_name
            del self._dvc_ver
            del self._encoding
            del self._cmd
            del self._challenge
            del self._response
        finally:
            self._log.debug ({'msg': f'$p${__VERSION__}$p$ $a${self._txt_destruct} {self._txt_finish}$a$', 'cls': __class__, 'acc': self._tc.success})
            del self._txt_construct
            del self._txt_destruct
            del self._txt_finish
            del self._txt_failed
            del self._txt_launch
            del self._txt_rtc_sync
            del self._txt_success
            gc.collect()

    def start ( self ) -> None:
        health = self.thread_health()
        if health in ('starting', 'running'):
            return
        if health == 'failed':
            raise RuntimeError ('Core 1 launch failed; reset required')
        if health != 'stopped':
            raise RuntimeError ('UART worker must exit before it can be started again')
        with state_lock:
            if shared['state'] != 'stopped':
                return
            shared['enabled'] = True
            shared['stop'] = False
            shared['state'] = 'starting'
            shared['last_progress'] = time.ticks_ms()
        try:
            self._log.info ({'msg': f'$v$Core 1 thread$v$ launching -> Interval: $p${self._thread_interval}$p$', 'acc': self._tc.waiting})
            entry = self.__main_thread
            gc.collect()
            started = time.ticks_ms()
            while True:
                try:
                    _thread.start_new_thread (entry, ())
                    self._dvc_cnctd = False
                    self._time_synchronised = False
                    return
                except OSError as ex:
                    # The previous Python entry can finish before RP2 releases the core.
                    if 'core1 in use' not in str(ex):
                        raise
                    if time.ticks_diff(time.ticks_ms(), started) >= 500:
                        with state_lock:
                            shared['state'] = 'failed'
                            shared['enabled'] = False
                        raise OSError ('core1 in use; reset required')
                    time.sleep_ms(20)
        except MemoryError:
            # Some RP2 firmware claims Core 1 before allocating its stack.
            with state_lock:
                shared['state'] = 'failed'
                shared['enabled'] = False
            raise
        except BaseException:
            with state_lock:
                if shared['state'] != 'failed':
                    shared['state'] = 'stopped'
            raise

    def stop ( self ) -> None:
        self._log.debug ({'msg': '$v$Core 1 thread$v$ $a$stopping...$a$', 'acc': self._tc.waiting})
        with state_lock:
            shared['enabled'] = False
        stopped = self.stop_core1_graceful()
        state = '$a$stopped$a$' if stopped else '$a$NOT stopped$a$'
        self._log.info ({'msg': f'$v$Core 1 thread$v$ {state}', 'acc': self._tc.critical})

    def pause_thread (self):
        self.__push_event ({'msg': '$v$Core 1 thread$v$ $a$pausing$a$', 'lvl': dl.INFO, 'cls': __class__, 'acc': self._tc.success})
        with state_lock:
            shared['pause'] = True

    def resume_thread (self):
        self.__push_event ({'msg': '$v$Core 1 thread$v$ $a$resuming$a$', 'lvl': dl.INFO, 'cls': __class__, 'acc': self._tc.success})
        with state_lock:
            shared['pause'] = False

    @property
    def thread_enabled(self):
        with state_lock:
            return shared['enabled']

    def thread_health(self, timeout=5.0):
        """Classify progress without waiting; timeout is the maximum progress age."""
        with state_lock:
            state = shared['state']
            progress = shared['last_progress']
        if state in ('stopped', 'failed'):
            return state
        limit = max(int(timeout * 1000), int(self._thread_interval * 4000))
        if progress is None or time.ticks_diff(time.ticks_ms(), progress) >= limit:
            return 'unresponsive'
        return state

    def core1_is_alive (self, timeout=5.0):
        return self.thread_health(timeout) in ('starting', 'running', 'stopping', 'paused')

    def stop_core1_graceful(self, wait=1.0):
        with state_lock:
            if shared['state'] == 'failed':
                return False
            if shared['state'] == 'stopped':
                shared['stop'] = False
                return True
            shared['stop'] = True
            shared['state'] = 'stopping'
        start = time.ticks_ms()
        while True:
            with state_lock:
                if shared['state'] == 'stopped':
                    return True
            if time.ticks_diff(time.ticks_ms(), start) >= int(wait * 1000):
                return False
            time.sleep_ms(20)

    def shutdown (self) -> bool:
        try:
           if self.thread_health() != 'stopped':
                # Signal to server that client is stopping
                self.stop ()
        except Exception as ex:
            self._log.trace ( {'msg': f'{ex}', 'cls': __class__} )
        finally:
            return True

########## COMMUNICATION HELPER METHODS ##########
    def sync_rtc (self, time_diff = 0):
        return self._sync_rtc (time_diff)

    async def sync_rtc_async(self, time_diff=0):
        return await self._sync_rtc_async(time_diff)

    def uart_state (self):
        uart_stats = self._uart.get_stats ()

        health = self.thread_health()
        if health == 'running':
            val = f'{tc.info}running{tc.end}'
            val += f'{tc.info} - active{tc.end}' if not shared.get('pause') else f'{tc.warning} - paused{tc.end}'
        elif health in ('starting', 'stopping'):
            val = f'{tc.warning}{health}{tc.end}'
        elif health == 'unresponsive':
            val = f'{tc.critical}unresponsive{tc.end}'
        else:
            val = f'{tc.critical}stopped{tc.end}'
        uart_stats.append (f'{self._tc.par}Thread:\t\t{val}')

        val = f'{tc.info}active{tc.end}' if self._hs_active else f'{tc.critical}not active{tc.end}'
        val += '' if not self._hs_paused else f'{tc.warning} - paused{tc.end}'
        uart_stats.append (f'{self._tc.par}Handshake:\t{val}')

        val = f'{tc.info}active{tc.end}' if self._sync_active else f'{tc.critical}not active{tc.end}'
        val += f'{tc.info} - synchronised{tc.end}' if self._time_synchronised else f'{tc.warning} - not synchronised{tc.end}'
        uart_stats.append (f'{self._tc.par}RTC sync:\t{val}')

        val = f'{tc.info}connected{tc.end}' if self._dvc_cnctd else f'{tc.critical}not connected{tc.end}'
        uart_stats.append (f'{self._tc.par}Device:\t\t{val}')

        uart_stats.append (f'{self._tc.par}EV buf used:\t{tc.success}{self._ev_buffer.size()}{tc.end}')
        uart_stats.append (f'{self._tc.par}EV buf free:\t{tc.success}{self._ev_buffer.space()}{tc.end}')
        return uart_stats

    def write (self, message):
        self._uart.send_line (message)

    def send_line (self, message):
        self._uart.send_line (message)

    def read (self):
        return self._uart.read_line ()

    def read_line (self):
        return self._uart.read_line ()

    def clear_buffers (self):
        self._uart.clear_buffers ()

    def clear_rx_buffer (self):
        self._uart.clear_rx_buffer ()

    def clear_tx_buffer (self):
        self._uart.clear_tx_buffer ()

    def get_rx_buffer (self):
        return self._uart.get_rx_buffer ()

    def get_tx_buffer (self):
        return self._uart.get_tx_buffer ()

    # returns the version of the client device
    def device_info ( self ):
        return self._dvc_name + ' ' + self._dvc_ver

    def device_name ( self ):
        return self._dvc_name

    def device_version ( self ):
        return self._dvc_ver

    def device_build ( self ):
        return self._dvc_build

    # Retrieve the device connection status
    @property
    def is_connected ( self ):
        return self._dvc_cnctd

    def connected ( self, value: bool ):
        self._dvc_cnctd = value

    @property
    def is_synchronised ( self ):
        return self._time_synchronised

    @property
    def hs_active (self):
        return self._hs_active
    @hs_active.setter
    def hs_active (self, value):
        self._hs_active = value

    @property
    def sync_active (self):
        return self._sync_active
    @sync_active.setter
    def sync_active (self, value):
        self._sync_active = value

    @property
    def thread_is_running (self) -> bool:
        return self.core1_is_alive()

    @property
    def thread_is_paused (self) -> bool:
        return self._thread_paused

    @property
    def watchdog_interval (self):
        return self._wd_interval
    @watchdog_interval.setter
    def watchdog_interval (self, value: int):
        self._wd_interval = value
