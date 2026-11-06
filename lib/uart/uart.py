__VERSION__ = "0.6.0.11"
# ruff: noqa: RUF100, UP025, UP004, I001, F401, BLE001, B012, S110
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
            self._ext_name  = 'na' # name of the server/external device
            self._ext_ver   = 'na' # version of the server/external device
            self._ext_build = 'na' # build number of the server/external device
            self._ev_buffer = event_buffer
            self._log.debug ({'msg': f'$p${__VERSION__}$p$ $a${self._txt_construct} {self._txt_launch}$a$', 'cls': __class__, 'acc': self._tc.waiting})
            self._dvc_cnctd:        bool = False
            self._thread_running:   bool = False
            self._hs_active:        bool = False
            self._hs_paused:        bool = False
            self._sync_active:      bool = False
            self._thread_paused:    bool = False
            self._cmd:              dict = {}
            self._cnf:              dict = file_io.load_json (cnf_fn)
            self._uart_buf_size:     int = self._cnf['uart_buf_size']
            self._encoding:          str = self._cnf['encoding']
            self._hs_rcv_delay:      int = self._cnf.get('hs_rcv_delay', 0.5)
            self._uart_interval:   float = self._cnf.get('uart_interval', 0.01)
            self._thread_interval: float = self._cnf.get('uart_thread_interval', 0.01)
            self._challenge:         str = self._cnf.get('challenge_phrase', 'ping')
            self._response:          str = self._cnf.get('challenge_response', 'pong')
            
            super().__init__(logger, self._cnf, self._tc)
            self._log.debug ({'msg': f'$p${__VERSION__}$p$ $a${self._txt_construct} {self._txt_finish}$a$', 'cls': __class__, 'acc': self._tc.success})
            
        except Exception:
            self._log.critical ({'msg': f'$p${__VERSION__}$p$ {self._txt_construct} {self._txt_failed}', 'cls': __class__})
            raise
        finally:
            if self._cnf:
                # Clear comms configuration
                self._cnf.clear()
                self._cnf = None
            gc.collect()

    def __destruct__ (self):
        try:
            self._log.debug ({'msg': f'$p${__VERSION__}$p$ $a${self._txt_destruct} {self._txt_launch}$a$', 'cls': __class__, 'acc': self._tc.waiting})
            super().__destruct__()
            self._dvc_cnctd = False
            self._ext_name = None
            self._ext_ver = None
            self._encoding = None
            self._cmd = None
            self._challenge = None
            self._response = None
        finally:
            self._log.debug ({'msg': f'$p${__VERSION__}$p$ $a${self._txt_destruct} {self._txt_finish}$a$', 'cls': __class__, 'acc': self._tc.success})
            self._txt_construct = None
            self._txt_destruct = None
            self._txt_finish = None
            self._txt_failed = None
            self._txt_launch = None
            self._txt_rtc_sync = None
            self._txt_success = None
            gc.collect()

    def start ( self ) -> None:
        gc.collect()
        health = self.thread_health()
        if health in ('starting', 'running'):
            return
        if health == 'failed':
            raise RuntimeError ('Core 1 launch failed; reset required')
        if health != 'stopped':
            raise RuntimeError ('UART worker must exit before it can be started again')
        self.disconnect('worker starting')
        with state_lock:
            if shared['state'] != 'stopped':
                return
            shared['enabled'] = True
            shared['stop'] = False
            shared['state'] = 'starting'
            shared['last_progress'] = time.ticks_ms()
        try:
            self._log.info (f'Core 1 thread launching -> Interval: {self._thread_interval}')
            entry = self.__main_thread
            gc.collect()
            started = time.ticks_ms()
            while True:
                try:
                    gc.collect()
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
        self.disconnect('local stop', notify=True)
        self._log.debug ('Core 1 thread stopping...')
        with state_lock:
            shared['enabled'] = False
        stopped = self.stop_core1_graceful()
        state = '$a$stopped$a$' if stopped else '$a$NOT stopped$a$'
        self._log.info (f'Core 1 thread {state}')

    def pause_thread (self):
        self.disconnect('worker paused', notify=True)
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
        self.disconnect('worker stopping')
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
    def _link_changed(self):
        self._dvc_cnctd = self._link.is_connected
        self._hs_active = self._link.state == 'handshaking'
        if not self._dvc_cnctd:
            self._rtc.reset()
            self._sync_active = False
            self._time_synchronised = False
            self._dvc_name = self._dvc_ver = self._dvc_build = 'na'
            self._uart.clear_buffers()
        else:
            parts = self._link.peer_name.rsplit(' ', 1)
            self._dvc_name = parts[0]
            self._dvc_ver = parts[1] if len(parts) == 2 else 'na'
            self._dvc_build = self._dvc_ver.rsplit('.', 1)[-1]
            self._wd_interval = self._link.peer_interval * self._link.multiplier

    def disconnect(self, reason='local disconnect', notify=False):
        self._link.disconnect(reason, notify)

    def service_connection(self):
        self._rtc.poll()
        self._time_synchronised = self._rtc.synced
        self._sync_active = self._rtc.active
        self._link.poll(self.can_send)
        if not self.is_connected:
            self.read_line()
            self._link.poll(self.can_send)

    def check_connection_timeout(self):
        self._link.check_timeout()

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
        return self.send_line(message)

    def send_line (self, message):
        if not self.is_connected:
            return False
        if isinstance(message, dict):
            message = {key: dict(value, tok=self._link.session) if isinstance(value, dict) else value
                       for key, value in message.items()}
        return self._uart.send_line(message)

    def read (self):
        return self.read_line()

    def read_line (self):
        for _ in range(8):
            raw = self._uart.read_line()
            if raw is None:
                return None
            try:
                message = json.loads(raw.decode(self._encoding))
            except (ValueError, UnicodeError):
                self._uart._push_event({'msg': 'Invalid UART JSON payload', 'lvl': dl.WARNING})
                continue
            if self._link.receive(message) or not self.is_connected:
                continue
            if self._rtc.receive(message):
                self._time_synchronised = self._rtc.synced
                self._sync_active = self._rtc.active
                continue
            return raw
        return None

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
        return self._ext_name + ' ' + self._ext_ver

    def device_name ( self ):
        return self._ext_name

    def device_version ( self ):
        return self._ext_ver

    def device_build ( self ):
        return self._ext_build

    # Retrieve the device connection status
    @property
    def is_connected ( self ):
        return self._dvc_cnctd

    def connected ( self, value: bool ):
        if not value:
            self.disconnect()
        elif not self._link.is_connected:
            raise ValueError('UART handshake required before connecting')

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
        with state_lock:
            return shared['pause']

    @property
    def watchdog_interval (self):
        return self._wd_interval
    @watchdog_interval.setter
    def watchdog_interval (self, value: int):
        self._wd_interval = value
