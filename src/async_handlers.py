__VERSION__ = "0.6.0.15"
# ruff: noqa: RUF100, UP025, UP004, I001, F401, UP041, BLE001, S110
# -*- coding: utf-8 -*-
try:
    import uasyncio as asyncio
except ImportError:
    import asyncio
try:
    import ujson as json
except ImportError:
    import json
import gc, sys, select
from   machine import PWM, Pin
from task_register import task_register

# AsyncHandlers class to handle asynchronous operations
# This class is a placeholder and can be extended with specific async methods, 
# which can be activated in async_tasks.json
class AsyncHandlers:
    def __init__(self):
        self.__bind_async_fncs ()
        super().__init__()

########## ASYNCHRONOUS TASK DEFINITIONS ##########
    # ASYNC Function to check the tank
    async def as_tank_check (self, name: str, task_info: dict):
        self.__log_task_started (name=name, task_info=task_info)
        gc.collect()
        try:
            while True:
                self._tank_ctrl.check_tank ()
                await asyncio.sleep (task_register[name]['intv'] * task_register[name]['mx'])
        except asyncio.CancelledError:
            self.__log_task_cancelling (name=name, task_info=task_info)
            raise
        except Exception:
            raise
    # ASYNC Function to check the tank
    async def as_tank_temp (self, name: str, task_info: dict):
        self.__log_task_started (name=name, task_info=task_info)
        gc.collect()
        try:
            while True:
                self._tank_ctrl.check_temperature ()
                await asyncio.sleep (task_register[name]['intv'] * task_register[name]['mx'])
        except asyncio.CancelledError:
            self.__log_task_cancelling (name=name, task_info=task_info)
            raise
        except Exception:
            raise
    # ASYNC Blinking LED
    async def as_led_blink (self, name: str, task_info: dict):
        self.__log_task_started (name=name, task_info=task_info)
        self._led = Pin (int  (self._led_pin), Pin.OUT)
        gc.collect()
        try:
            while True:
                if task_register[name]['state'] != self.as_state.PAUSED:
                    # Control the blink rate of the LED, 
                    self._led.toggle()
                await asyncio.sleep (task_register[name]['intv'] * task_register[name]['mx'])
        except asyncio.CancelledError:
            self._led.off()
            self.__log_task_cancelling (name=name, task_info=task_info)
            raise
    # ASYNC Dimming LED
    async def as_led_pwm (self, name: str, task_info: dict):
        brightness = 1000
        direction  = 1
        step       = task_info.get ('pwm_step', 32)
        interval   = task_info.get ('pwm_interval', 0.2)
        try:
            self._led_pin = int (self._led_pin)
        except ValueError:
            raise ValueError (f'Invalid LED pin: $p${self._led_pin}$p$ - must be numeric!')
        self._led = PWM (self._led_pin, freq= task_info.get ('pwm_freq', 1000)) # type: ignore
        self.__log_task_started (name=name, task_info=task_info)
        gc.collect()
        try:
            while True:
                # Update the brightness
                brightness += step * direction
                if brightness >= 1023:
                    brightness = 1023
                    direction = -1  # Start dimming
                elif brightness <= 0:
                    brightness = 0
                    direction = 1   # Start brightening
                # Apply the brightness
                self._led.duty_u16(brightness * 64)  # type: ignore # Scale 0-1023 to 0-65535
                await asyncio.sleep (interval) # Adjust for desired speed of change 
        except asyncio.CancelledError:
            self.__log_task_cancelling (name=name, task_info=task_info)
            await asyncio.sleep (0.1)
            self._led.deinit() # type: ignore
            self._led = None # type: ignore
            raise
        except Exception:
            raise
    # ASYNC memory check
    async def as_memory ( self, name: str, task_info: dict):
        self.__log_task_started (name=name, task_info=task_info)
        gc.collect()
        try:
            while True:
                if task_register[name]['state'] != self.as_state.PAUSED:
                    gc.collect()
                await asyncio.sleep (task_register[name]['intv'] * task_register[name]['mx'])
        except asyncio.CancelledError:
            self.__log_task_cancelling (name=name, task_info=task_info)
            raise
    # ASYNC Function to read input character by character    
    async def as_key_read (self, name: str, task_info: dict):
        """Continuously read input character by character."""
        self.__log_task_started (name=name, task_info=task_info)
        try:
            while True:
                if not self._shutdown and sys.stdin in select.select([sys.stdin], [], [], 0)[0] and not self._processing_cmd:  # Check 
                        await self._cmd_buffer.add_char(sys.stdin.read(1))
                await asyncio.sleep (task_register[name]['intv'] * task_register[name]['mx'])
        except asyncio.CancelledError:
            self.__log_task_cancelling (name=name, task_info=task_info)
            raise
        except Exception:
            raise
    # ASYNC Function to check if there is usb char/string waiting, this method uses the poll object.
    async def as_key_cmd (self, name: str, task_info: dict):
        # Set up the poll object for monitoring the usb port
        self.__log_task_started (name=name, task_info=task_info)
        cmd: str = ''
        try:
            while True:
                if not self._shutdown and self._cmd_buffer.has_cmd:
                    cmd = self._cmd_buffer.get_cmd()
                    if cmd != '\n':
                        data = []
                        if ' ' in cmd:
                            data = cmd.strip().split(' ')
                        else:
                            data = [cmd.strip()]
                        
                        if not data:
                            continue
                        
                        if data[0].lower() == 'exit':
                            self.stop()
                        else:
                            if data[0].lower() in self._cmds_main:
                                self._log.debug ({'msg': f'$f$as_process_cmd$f$ received: $p${data}$p$'})
                                asyncio.create_task (self._process_command (*data))
                                data = []
                            else:
                                self._log.warning ({'msg':f'Unknown Command: $a${data[0]}$a$', 'acc': self._tc.critical})
                        gc.collect()
                await asyncio.sleep (task_register[name]['intv'] * task_register[name]['mx'])
        except asyncio.CancelledError:
            self.__log_task_cancelling (name=name, task_info=task_info)
            raise
        except KeyboardInterrupt:
            raise
        except Exception:
            raise
    # ASYNC receive coms transmissions
    async def as_uart_cmd(self, name: str, task_info: dict):
        self.__log_task_started(name=name, task_info=task_info)
        try:
            while True:
                if (task_register[name]['state'] != self.as_state.PAUSED
                        and self._uart.is_connected and not self._uart.thread_is_paused):
                    req = self._uart.read_line()
                    if req:
                        self._log.debug({'msg': f'UART received: {req.decode(self._encoding).strip()}'})
                await asyncio.sleep (task_register[name]['intv'] * task_register[name]['mx'])
        except asyncio.CancelledError:
            self.__log_task_cancelling(name=name, task_info=task_info)
            raise
    # ASYNC uart watchdog - checks whether client is connected
    async def as_uart_watchdog(self, name: str, task_info: dict):
        self.__log_task_started(name=name, task_info=task_info)
        try:
            while True:
                if (task_register[name]['state'] != self.as_state.PAUSED
                        and not self._uart.thread_is_paused):
                    self._uart.check_connection_timeout()
                await asyncio.sleep(task_register[name]['intv'] * task_register[name]['mx'])
        except asyncio.CancelledError:
            self.__log_task_cancelling(name=name, task_info=task_info)
            raise
    # ASYNC get event log data from coms object
    async def as_uart_event (self, name: str, task_info: dict):
        self.__log_task_started (name=name, task_info=task_info)
        gc.collect()
        try:
            while True:
                if task_register[name]['state'] != self.as_state.PAUSED:
                    while len (self._ev_buffer) > 0:
                        event = self._ev_buffer.get()
                        if isinstance(event, dict) and event !={}:
                            if 'uart_tx' in event:
                                data = event.pop('uart_tx')
                                event['lvl'] = self.dbg_lvls.DEBUG
                                event['msg'] = f'{self._tc.info}Writing: {self._tc.par}{data}{self._tc.end}'
                            elif 'uart_rx_error' in event:
                                data = event.pop('uart_rx_error')
                                event['lvl'] = self.dbg_lvls.ERROR
                                event['msg'] = f'UART frame rejected (CRC/format): {data!r}'
                            if 'ts' not in event:
                                event['ts'] = self._log.get_time_stamp()
                                
                            level = event.get('lvl', self.dbg_lvls.OFF)
                            
                            if   level == self.dbg_lvls.OFF:      return
                            elif level == self.dbg_lvls.DEBUG:    self._log.debug   (event)
                            elif level == self.dbg_lvls.INFO:     self._log.info    (event)
                            elif level == self.dbg_lvls.WARNING:  self._log.warning (event)
                            elif level == self.dbg_lvls.ERROR:    self._log.error   (event)
                            elif level == self.dbg_lvls.CRITICAL: self._log.critical(event)
                            elif level == self.dbg_lvls.TRACE:    self._log.trace   (event)
                            elif level == self.dbg_lvls.PRINT:    self._log.aprint  (event['msg'])
                        await asyncio.sleep(0)
                await asyncio.sleep (task_register[name]['intv'] * task_register[name]['mx'])
        except asyncio.CancelledError:
            self.__log_task_cancelling (name=name, task_info=task_info)
            raise
        except Exception:
            raise
    # ASYNC Function to connect to uart
    async def as_uart_connect(self, name: str, task_info: dict):
        self.__log_task_started(name=name, task_info=task_info)
        try:
            while True:
                if task_register[name]['state'] != self.as_state.PAUSED:
                    if self._uart.thread_health() != 'running' or self._uart.thread_is_paused:
                        self._uart.disconnect('UART worker unavailable')
                    else:
                        self._uart.service_connection()
                await asyncio.sleep(task_register[name]['intv'] * task_register[name]['mx'])
        except asyncio.CancelledError:
            self._uart.disconnect('connection task cancelled', notify=True)
            self.__log_task_cancelling(name=name, task_info=task_info)
            raise
    # ASYNC Function to synchronise rtc with server, default every 30 seconds 
    async def as_rtc_sync(self, name: str, task_info: dict):
        self.__log_task_started(name=name, task_info=task_info)
        try:
            while not self._uart.is_synchronised:
                if (task_register[name]['state'] != self.as_state.PAUSED
                        and self._uart.is_connected and not self._uart.thread_is_paused):
                    self._uart.sync_rtc()
                await asyncio.sleep(task_register[name]['intv'] * task_register[name]['mx'])
        except asyncio.CancelledError:
            self.__log_task_cancelling(name=name, task_info=task_info)
            raise
    # ASYNC Update server via socket, default every 10 seconds 
    async def as_update ( self, name: str, task_info: dict):
        self.__log_task_started (name=name, task_info=task_info)
        gc.collect()
        try:
            while True:
                if self._uart.is_connected and self._uart.can_send and task_register['as_tank_check']['state'] not in (self.as_state.PAUSED, self.as_state.STOPPED):
                    self.state['sys']['client']['c_tmp'] = self._helpers.get_core_temp()
                    self.state['sys']['client']['mem_f'] = gc.mem_free()  # type: ignore
                    self.state['sys']['client']['mem_a'] = gc.mem_alloc() # type: ignore
                    self._uart.post ({'status': {'tank': self.state['tank']}})
                    self._uart.post ({'status': {'dvcs': self.state['dvcs']}})
                    self._uart.post ({'status': {'sys':  self.state['sys']}})
                    self._uart.post ({'status': {'mem':  self.state['mem']}})
                    gc.collect()
                await asyncio.sleep (task_register[name]['intv'] * task_register[name]['mx'])
        except asyncio.CancelledError:
            self.__log_task_cancelling (name=name, task_info=task_info)
            raise
        except Exception:
            raise
    # Cancel all asynchronous tasks 
    async def as_monitor (self, name: str, task_info: dict):
        self.__log_task_started (name=name, task_info=task_info)
        gc.collect()
        while True:
            try:
                if task_register[name]['state'] != self.as_state.PAUSED:
                    self.task_manager.task_status_all (failed_only = True)
                    val = f'{self._tc.info}{self.s2t[self.as_state.RUNNING]}{self._tc.end}' if not self._uart.thread_is_paused else f'{self._tc.waiting}{self.s2t[self.as_state.PAUSED]}{self._tc.end}'
                    self._log.debug ({'msg': f'$v$Core 1 thread$v$ {val}'})
                    if self.task_manager.get_failed_task_count () > 3: 
                        # There is a major problem if there are more than 3 failed tasks
                        self.stop (exc=True)
                await asyncio.sleep (task_register[name]['intv'] * task_register[name]['mx'])
            except asyncio.CancelledError:
                self.__log_task_cancelling (name=name, task_info=task_info)
                raise
            except Exception as ex:
                self._log.trace ({'exc': ex, 'cls': __class__})
                raise
    # Async function to check thread status
    async def as_thread_monitor (self, name: str, task_info: dict):
        self.__log_task_started (name=name, task_info=task_info)
        gc.collect()
        try:
            while True:
                if (task_register[name]['state'] != self.as_state.PAUSED
                        and self._uart.thread_health() != 'running'):
                    self._uart.disconnect('UART worker unavailable')
                await asyncio.sleep(task_register[name]['intv'] * task_register[name]['mx'])
        except asyncio.CancelledError:
            self.__log_task_cancelling(name=name, task_info=task_info)
            raise
    # ASYNC task to monitor which tasks are running
    async def as_task_monitor(self, name: str, task_info: dict):
        self.__log_task_started(name=name, task_info=task_info)
        try:
            while True:
                if (task_register[name]['state'] != self.as_state.PAUSED
                        and self._uart.thread_health() != 'running'):
                    self._uart.disconnect('UART worker unavailable')
                await asyncio.sleep(task_register[name]['intv'] * task_register[name]['mx'])
        except asyncio.CancelledError:
            self.__log_task_cancelling(name=name, task_info=task_info)
            raise

########## HELPER METHODS ##########
    def __log_task_started (self, name: str, task_info: dict):
        if task_info['id'] == 0:
            task_info['id'] = task_register.get(name, {}).get('task_id', 0)
            
        self._log.info ({'msg': f'$f${name}$f$ $i${task_info['id']}$i$ $a$has started$a$. Interval = $p${task_info['intv']} sec$p$', 'acc': self._tc.success})
    def __log_task_cancelling (self, name: str, task_info: dict):
        self._log.debug ({'msg': f'$f${name}$f$ $i${task_info['id']}$i$$a$ cancelled$a$', 'acc': self._tc.warning})
        
    def __log_task_paused (self, name: str, task_info: dict):
        self._log.info ({'msg': f'$f${name}$f$ $i${task_info['id']}$i$$a$ {self.as_state.PAUSED}$a$', 'acc': self._tc.waiting})
        
    def __bind_async_fncs (self):
        for task_name, task_info in task_register.items():
            cls_name = task_info.get ('cls', None)
            if not cls_name:
                continue # static or direct function
            instance = self._class_map.get (cls_name)
            if not instance:
                self._log.warning ({'msg': f'Class $p${cls_name}$p$ not found', 'src': __name__})
                continue
            try:
                coro = getattr (instance, task_name)
                if callable (coro):
                    task_register[task_name]['function'] = coro
                else:
                    self._log.warning ({'msg': f'Function $p${task_name}$p$ in class $p${cls_name}$p$ is not callable', 'src': __name__})
            except AttributeError:
                self._log.warning ({'msg': f'Function $p${task_name}$p$ not found in class $p${cls_name}$p$', 'src': __name__})
########## ASYNCHRONOUS TEST METHODS ##########
    # ASYNC task to create error task
    async def as_error (self, name: str, task_info: dict):
        self.__log_task_started (name=name, task_info=task_info)
        gc.collect()
        try:
            err = 'Test Error'
            cnt: int = task_register[name].get ('retry_count', 0)
            while True:
                if cnt == 0:
                    raise KeyError (err)
                if cnt == 1:
                    raise ValueError (err)
                if cnt == 2:
                    raise ZeroDivisionError (err)
                if cnt == 3:
                    raise OSError (err)
                if cnt == 4:
                    raise TypeError (err)
                if cnt == 5:
                    raise MemoryError (err)
                await asyncio.sleep (task_register[name]['intv'] * task_register[name]['mx'])
        except asyncio.CancelledError:
            self.__log_task_cancelling (name=name, task_info=task_info)
            raise
