__VERSION__ = "0.6.0.7"
# ruff: noqa: RUF100, UP025, UP004, I001, F401, BLE001, E722
# -*- coding: utf-8 -*-
########## CLASS IMPORTS ##########
import sys
import os
try:
    import uasyncio as asyncio
except:
    import asyncio
try:
    import ujson as json
except:
    import json

import gc, select, re
from   machine          import Pin, PWM, RTC
from   collections      import OrderedDict
try:
    from   tank_controller  import TankController
    from   helpers          import helpers, FixedSizeFIFO as FIFO
    from   uart.uart        import UARTComms
    from   logger.logger    import Logger
    from   task_manager     import TaskManager
    from   async_handlers   import AsyncHandlers
    from   cmd_handlers     import CommandHandlers
except Exception as ex:
    sys.print_exception (ex)
    raise ImportError (f'{__name__}: {ex}')

class Processor (CommandHandlers, AsyncHandlers):
    tc = None
########## CLASS INITIALISATION ##########
    def __init__ (self,
                  logger: Logger,
                  file_io,
                  tc, 
                  config: dict,
                  cb_exit, 
                  name: str,
                  help_fncs,
                  dbg_lvls):
    ########## CLASS INITIALISATION AND INIT METHODS ##########
        self._log   = logger
        self._fio   = file_io
        self._tc    = tc
        self._log.debug ({'msg': f'$p${__VERSION__}$p$ $a$constructor launched...$a$', 'cls': __class__, 'cls': __class__, 'src': __name__, 'acc': self._tc.waiting})
        self._cmd_buffer  = AsyncUARTBuffer(self._log.reader_lock(),logger.aReader())
        if cb_exit is None:
            raise ValueError (f'{'init'}: Parameter cb_exit cannot be None!')
    ########## LOAD PARAMETERS #########
        self._cb_parent_shutdown = cb_exit
        self.help_fncs           = help_fncs
        self._helpers: helpers   = helpers (tc=tc)
        self.state: dict         = {}
        self.dbg_lvls            = dbg_lvls
        self.task_manager: TaskManager
    ########## LOAD SETTINGS FROM CONFIG FILE ##########
        # Load async task json file
        self.task_register: dict
        try:
            self.task_register = file_io.load_json (fn=config['files']['async_tasks'])
            self.task_register = OrderedDict (sorted (self.task_register.items(), key=lambda item: item[1]["idx"]))
            self.state.setdefault ('tank', config.get('tank').copy())
            self.state.setdefault ('sys',  config.get('sys').copy())
            self.state.setdefault ('dvcs', config.get('dvcs').copy())
            self.state.setdefault ('tmp',  config.get('tmp').copy())
            self._pin_ready         = Pin (config.get('pin_ready', 4), Pin.IN, Pin.PULL_DOWN)
            self._challenge:    str = config.get('challenge_phrase', 'ping')
            self._response:     str = config.get('challenge_response', 'pong')
            self._my_info:      str = f'{config.get('self_name', 'PTCC')} ({__VERSION__})'
            self._fn_cmd_dict:  str = config['files']['cmd_dict']
            self._mx_fail_tsks: int = int (config.get('max_failed_task_count', 3))
        except (KeyError, ValueError, OSError) as ex:
            self._log.trace ({'exc': ex, 'cls': __class__})
            raise
    ########## CLASS VARIABLE INITIALISATION ##########
        self._exit_dly: int             = 2
        self._mem_threshold: int        = 0
        self._tank_ctrl: TankController = None 
        self._led:       Pin            = None
        self._uart:      UARTComms      = None 
        self._destructed: bool          = False
        self._processing_cmd: bool      = False
        self._shutdown: bool            = False
        self._ev_buf_size: int          = config.get('ev_buf_size')
        self._ev_buffer                 = FIFO (self._ev_buf_size)
        self._encoding: str             = config.get('text_encoding', 'utf-8')
        self._led_pin: int              = config['pins']['led']
        self._uart_wd_interval: int     = 10
        self.as_state                   = TaskManager.State
        self.s2t                        = TaskManager.S2T
    ########## CREATE A CLASS BINDING MAP ##########
        self._class_map = {"Processor": self}
        super().__init__ ()
    ########## INITIALISE OBJECTS ##########
        try:
            # Shared event to reset the watchdog
            self._uart_watchdog_event = asyncio.ThreadSafeFlag()
            self._tank_ctrl = TankController (
                logger=logger, 
                file_io=file_io, 
                cnf_fn=config['files']['tank_config'], 
                tc=self._tc, 
                state=self.state, 
                help_fcnts=help_fncs
            )
            self._class_map.setdefault ('TankController', self._tank_ctrl)
            self._uart = UARTComms (
                logger=logger, 
                file_io=file_io, 
                cnf_fn=config['files']['comms'], 
                tc=self._tc,
                name=os.uname().machine,
                event_buffer=self._ev_buffer
            )
            self._mem_threshold = (gc.mem_free() + gc.mem_alloc()) // 4
            gc.threshold (self._mem_threshold)
            self._log.info ({'msg': f'$a$Memory threshold set$a$ $p$@ {self._mem_threshold} bytes$p$', 'acc': self._tc.success, 'src': __name__})
            self.__bind_async_fncs()
            self.task_manager = TaskManager (
                logger=self._log, 
                    tc=self._tc, 
                    task_register=self.task_register, 
                    cb_shutdown=self.shutdown
                )
            self._log.debug ({'msg': f'$p${__VERSION__}$p$ $a$constructor finished$a$', 'cls': __class__, 'src': __name__, 'acc': self._tc.success})
        except Exception as ex:
            self._log.trace ({'exc': ex, 'cls': __class__, 'src': __name__})
            raise
        finally:
            self._class_map.clear()
            self._class_map = None
            gc.collect()
    ###### METHODS ######
    def __bind_async_fncs (self):
        for task_name, task_info in self.task_register.items():
            cls_name = task_info.get('cls', None)
            if not cls_name:
                continue
            instance = self._class_map.get (cls_name)
            if not instance:
                self._log.warning ({'msg': f'Class $p${cls_name}$p$ not found', 'src': __name__})
                continue
            try:
                coro = getattr (instance, task_name)
                if callable (coro):
                    self.task_register[task_name]['fnc'] = coro
                else:
                    self._log.warning ({'msg': f'$p${task_name}$p$ in class $p${cls_name}$p$ is not callable', 'src': __name__})
            except AttributeError:
                self._log.warning ({'msg': f'$p${task_name}$p$ not found in class $p${cls_name}$p$', 'src': __name__})
########## CLASS DESTRUCTORS AND CLEANUP METHODS ##########
    # Class destructor
    def destructor (self):
        if self._destructed:
            return
        else:
            self._log.debug ({'msg': f'$p${__VERSION__}$p$ $a$destructor launched...$a$', 'cls': __class__, 'src': __name__, 'acc': self._tc.waiting})
            # Delete asynchronous task manager
            if self.task_manager is not None:
                self.task_manager = None
            self.task_register.clear()
            self.task_register = None
            self._uart_watchdog_event = None
            self._tank_ctrl = None
            for key in self.state:
                self.state[key].clear()
            self.state.clear()
            self.state = None
            self._ev_buffer = None
            self._cmd_buffer = None
            self._input = None
            self._uart = None
            self._encoding = None
            self._fn_cmd_dict = None
            self._log.debug ({'msg': f'$p${__class__}$p$ $a$destructor finished...$a$', 'cls': __class__, 'acc': self._tc.success})
            self._destructed = True
            gc.collect()

########## CLASS PROPERTIES ##########
    def __version (self):
        return __VERSION__
    def __repr__ (self):
        return f'{self.__class__} Ver.: ({__VERSION__})'
    def __str__ (self):
        return f'{self.__class__}'
########## CLASS DATA, CMD PROCESSING AND HELPER METHODS ##########
    async def analyse_uart_cmd (self, cmd: dict):
        cmd_type = next(iter(cmd.keys()))
        if cmd_type in self._server_cmds:
            target  = cmd.get(cmd_type).get('tgt',  None) 
            device  = cmd.get(cmd_type).get('dvc',  None)
            action  = cmd.get(cmd_type).get('act',  None)
            data    = cmd.get(cmd_type).get('data', None)
            request = []
            if cmd_type == 'cmd':
                request = [target, device, action, data]
            elif cmd_type == 'req':
                token = cmd.get(cmd_type).get('tok', None)
            elif cmd_type == 'msg':
                # Print the message and return
                self._log.aprint (f'Message received: {cmd[cmd_type]['data']}')

            # Forward the request to the command processor
            asyncio.create_task (self.process_command (*request))
########## CLASS DATA, CMD PROCESSING AND HELPER METHODS ##########
    async def _convert_uart_cmd (self, cmd: dict):
        __fnc_name = '_convert_uart_cmd'
        key = next(iter(cmd.keys())) 
        
        if key not in self._client_reqs:
            self._log.warning({
                'msg': f'Command type $a${key}$a$ not supported',
                'fnc': __fnc_name,
                'acc': self._tc.critical
            })
            return

        target  = cmd[key].get('tgt')
        device  = cmd[key].get('dvc')
        action  = cmd[key].get('act')
        data    = cmd[key].get('data')
        token   = cmd[key].get('tok')
        event   = cmd[key].get('evt', {})
        request = []

        # Status update received
        if key == 'sta':
            self._log.aprint(f'Status update: $v${device}$v$ $p${data}$p$')
            
        # Request received    
        elif key == 'req':
            if cmd['req'].get('act') == 'exit':
                self._log.warning ({'msg': f'Device $v${self._uart.device_name()}$v$ requested exit'})
                self.task_manager.cancel_task (task_name='as_uart_watchdog')
                self.task_manager.cancel_task (task_name='as_uart_cmd')
                self._uart.set_connection_state (False)
            else:
                request = [target, device, action, data]
                asyncio.create_task(self._process_command(*request))
                
        # Log event received
        elif key == 'log':
            event.setdefault('dvc', self._uart.device_name())
            lvl = event.get('lvl', 'off')
            self._log.log_event (lvl, event)
        
        # Message received
        elif key == 'msg':
            msg_data = cmd[key].get('data')
            self._log.aprint(f"Message received: {msg_data}")
    async def _process_command ( self, *args ):
        try:
            while self._processing_cmd:
                await asyncio.sleep (0.1)
            # Prevent cascade processing of command 
            self._processing_cmd = True
            cmd:  str = args[0].lower()
            par1: str = args[1].lower()  if len(args) > 1 else None
            par2: str = args[2].lower()  if len(args) > 2 else None
            params    = args[3:] if len(args) > 3 else []
            
            ##### Main commands ######
            if cmd == 'exit':
                self._log.info ({'msg': f'$f$as_process_cmd$f$ received: $p${args}$p$'})
                self.stop (exc=False)
            # Process the command
            self.handle (cmd=cmd, par1=par1, par2=par2, params=params)
        except (NotImplementedError, KeyError) as ex:
            self._log.warning ({'msg': str (ex)})
        except OSError:
            self._log.error ({'msg':f'Error accessing $p${self._fn_cmd_dict}$p$'})
        except Exception as ex:
            self._log.trace ({'exc': ex, 'cls': __class__})
        finally:
            gc.collect()
            self._processing_cmd = False
    def __sys_state (self):
        try:
            self._log.aprint (f'{self._tc.ul}{self._tc.success}Allocated Memory:{self._tc.end} {self._tc.par}\t{self.sys_state['srvr']['mem_a']}{self._tc.end}')
            self._log.aprint (f'{self._tc.ul}{self._tc.success}Free Memory:{self._tc.end} {self._tc.par}\t\t{self.sys_state['srvr']['mem_f']}{self._tc.end}')
            self._log.aprint (f'{self._tc.ul}{self._tc.success}Server CPU Temp:{self._tc.end} {self._tc.par}\t{self.sys_state['srvr']['c_tmp']}{self._tc.end}')
        except KeyError:
            pass

########## HELPER METHODS ##########
    # Start process class asynchronous tasks
    def start (self):
        try:
            # Start the communication module
            if self._uart is not None:
                self._uart.start ()
            # Run all asynchronous tasks perpetually
            asyncio.run (self.task_manager.tm_main ())
        except OSError as ex:
            self._log.trace ({'exc': ex, 'cls': __class__})
        except KeyboardInterrupt:
            self._log.warning ({'msg': 'Program Interrupted by Ctrl+C', 'cls': __class__, 'src': __name__, 'fnc': 'start'})
            self.stop(exc=True)
        except Exception as ex:
            self._log.trace ({'msg': f'Exception: {ex}', 'cls': __class__, 'src': __name__, 'fnc': 'start'})
            self.stop(exc=True)
    def stop (self, exc: bool = False):
        # Prevent shutdown cascade
        if not self._shutdown:
            if not exc:
                self._log.info ({'msg': '$a$Executing shutdown request...$a$', 'src': __name__, 'acc': self._tc.waiting})
            else:
                self._log.info ({'msg': '$a$Shutting down due to exception...$a$', 'src': __name__, 'acc': self._tc.waiting})                
            # Set the shutdown flag to signal tm_main to execute controlled shutdown
            # Using a flag rather than calling shutdown directly prevents a hung shutdown in the async engine
            self._shutdown = True
            if self.task_manager and self.task_manager.is_alive:
                    self.task_manager.stop()
    def shutdown (self):
        # NOTE: The ORDER of the object shutdown is IMPORTANT:
        # 1) shutdown the UART thread coms, so that the procedure will notify the server of the client shutdown 
        #    and clear transmit, receive and event buffers 
        # 2) shutdown the task manager, which in turn will all running tasks and cleanup memory 
        # 3) cleanup the coms module
        # 4) Shutdown the worker process (tank controller), which in turn will release all configured devices
        #    and cleanup memory
        # 5) Lastly call the parent shutdown procedure to gracefully exit the whole program
        try:
            if self._uart is not None:
                self._uart.shutdown ()
            # Shutdown and cleanup Task Manager
            if self.task_manager and self.task_manager.is_alive:
                    self.task_manager.shutdown()
                    self.task_manager.check_tasks_done()
                    self.task_manager.destructor()
            # Cleanup the UART Comms module
            if self._uart is not None:
                self._uart.__destruct__()
            # Shutdown the tank controller 
            if self._tank_ctrl is not None:
                self._tank_ctrl.__destruct__()
            # Call the parent shutdown process, which will call the processor destructor
            self._cb_parent_shutdown ()
        except Exception as ex:
            self._log.trace ({'exc': ex, 'cls': __class__})
    def __sys_state (self):
        self._log.aprint (f'\n{self._tc.ul}{self._tc.yellow}Allocated Memory: {self._tc.par}{self.state['sys']['srvr']['mem_a']}{self._tc.end}')
        self._log.aprint (f'\n{self._tc.ul}{self._tc.yellow}Free Memory: {self._tc.par}{self.state['sys']['srvr']['mem_f']}{self._tc.end}')
        self._log.aprint (f'\n{self._tc.ul}{self._tc.yellow}Server CPU Temperature{self._tc.par}{self.state['sys']['srvr']['c_tmp']}{self._tc.end}')
    def task_interval (self, task_name: str, params: list = []):
        self.task_manager.task_interval (task_name=task_name, params=params)
    def dir_async_fnc (self, cls_name: str):
        return [name for name in dir(cls_name) if callable(getattr(cls_name, name)) and name.startswith('as_')]

########## ASYNCHRONOUS INPUT CLASS #########
class AsyncUARTBuffer:
    """Manages shared input buffer and synchronization."""
    def __init__(self, lock, reader):
        self.buffer   = ''
        self.cmd      = ''
        self.lock     = lock
        self._reader  = reader
        self._has_cmd = False

    async def add_char(self, char):
        """Append a character to the buffer."""
        async with self.lock:
            if char in ("\n", "\r"):  # Input complete
                self.cmd = self.buffer + char
                self._has_cmd = True
                self.buffer = ""  # Clear buffer after use
            else:
                self.buffer += char

    def get_cmd (self):
        if len(self.cmd) > 0:
            cmd = self.cmd
            self.cmd = ''
            self._has_cmd = False
            return cmd
            
    async def get_input (self, prompt="", end=''):
        buffer = await self._reader.read (prompt, end)
        return buffer

    @property
    def has_cmd (self):
        return self._has_cmd

class CommandError (Exception):
    def __init__(self, cmd: str, action: str, parameter: str = ''):
        """
        Initializes a new instance of the exception class.

        Args:
            message (str): The error message.
            source (str): The source of the error.

        Returns:
            None
        """
        
        self.message = f'Invalid Command: $x${cmd}$x$, Action: $a${action}$a$'
        if parameter != '':
            self.message += f', Parameter: $p${parameter}$p$'   
        super().__init__(self.message)
        
    def __str__(self):
        return repr(self.message)
