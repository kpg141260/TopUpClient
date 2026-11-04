__VERSION__ = "0.6.0.7"
# ruff: noqa: RUF100, UP025, UP004, I001, F401
# -*- coding: utf-8 -*-
try:
    import uasyncio as asyncio
except ImportError:
    import asyncio

import gc

class CommandHandlers:
########## CLASS INIT AND DESTRUCTOR ##########
    def __init__(self):
        self._cmds_main:   list = []
        self._cmds_task:   list = []
        self._cmds_tank:   list = []
        self._cmds_system: list = []
        self._cmds_uart:   list = []
        self._cmds_srvr:   list = []
        self._prefix:       str  = ''
        self.load_cmd_lists ()
        super().__init__()

    def __destruct__(self):
        try:
            self._cmds_main.clear()
            self._cmds_task.clear()
            self._cmds_tank.clear()
            self._cmds_system.clear()
            self._cmds_uart.clear()
            self._cmds_srvr.clear()
            self._cmds_tank = None
            self._cmds_main = None
            self._cmds_task = None
            self._cmds_system = None
            self._cmds_uart = None
            self._cmds_srvr = None
            self._prefix = None
            #super().__destruct__()
        finally:
            gc.collect()
########## CLASS PROPERTIES ##########
    def __version__ (self):
        return __VERSION__
    def __repr__ (self):
        return f'{self.__class__} Ver.: ({__VERSION__})'
    def __str__ (self):
        return f'{self.__class__}'

#### MAIN FUNCTIONS ######
    def load_cmd_lists (self):
        cmds = self._fio.load_json (self._fn_cmd_dict)
        try:
            self._cmds_main   = list (cmds.keys())
            self._cmds_task   = cmds['task']
            self._cmds_system = cmds['system']
            self._cmds_uart   = cmds['uart']
            self._cmds_tank   = cmds['tank']
            self._cmds_srvr   = cmds['srvr']
            self._prefix      = cmds['prefix']
        except KeyError as ex:
            raise KeyError (f'Section {self._tc.critical}{ex}{self._tc.end} not found in cmd list {self._tc.par}{self._fn_cmd_dict}{self._tc.end}')
        except OSError:
            raise OSError (f'Error accessing {self._tc.par}{self._fn_cmd_dict}{self._tc.end}')

    def handle (self, cmd, par1, par2=None, params=None):
        try:
            # Build the dispatch table dynamically from the JSON list
            dispatch_map = {}
            if cmd == 'task':
                _cmd_list = self._cmds_task
            elif cmd == 'system':
                _cmd_list = self._cmds_system
            elif cmd == 'uart':
                _cmd_list = self._cmds_uart
            elif cmd == 'tank':
                _cmd_list = self._cmds_tank
            elif cmd == 'srvr':
                _cmd_list = self._cmds_srvr
            else:
                raise NotImplementedError(f'Command $x${cmd}$x$ not implemented in {__class__}')
            
            # Process the command and parameters
            for command in _cmd_list:
                handler_name = f'{self._prefix}{cmd}_{command}'
                if hasattr(self, handler_name):
                    dispatch_map[command] = getattr(self, handler_name)
                else:
                    self._log.warning({'msg': f'Handler $x${handler_name}$x$ not found in {__class__}', 'src': __name__})
            # Call the handler if it exists
            handler = dispatch_map.get(par1)
            if handler:
                handler (par2, params)
            else:
                raise NotImplementedError(f'Handler for command $x${cmd} {par1}$x$ not implemented in {__class__}')
        finally:
            dispatch_map = None
            _cmd_list = None
            gc.collect()

####### COMMAND HANDLER METHODS ######
###### TANK COMMANDS ######
    def _hdlr_tank_state(self, par2, params):
        self.tank_ctrl.print_tank_state()
    def _hdlr_tank_chiller(self, par2, params):
        if not par2:
            raise ValueError('Missing action parameter')
        if par2 == 'on':
            self.tank_ctrl.relay_c.on()
        elif par2 == 'off':
            self.tank_ctrl.relay_c.off()
        elif par2 == 'toggle':
            self.tank_ctrl.relay_c.toggle()
        else:
            raise ValueError(f'Invalid action $x${par2}$x$')
    def _hdlr_tank_pump (self, par2, params):
        if not par2:
            raise ValueError('Missing action parameter')
        if par2 == 'on':
            self.tank_ctrl.relay_p.on()
        elif par2 == 'off':
            self.tank_ctrl.relay_p.off()
        elif par2 == 'toggle':
            self.tank_ctrl.relay_p.toggle()
        else:
            raise ValueError(f'Invalid action $x${par2}$x$')
    def _hdlr_tank_valve (self, par2, params):
        if not par2:
            raise ValueError('Missing action parameter')
        if par2 == 'on':
            self.tank_ctrl.relay_v.on()
        elif par2 == 'off':
            self.tank_ctrl.relay_v.off()
        elif par2 == 'toggle':
            self.tank_ctrl.relay_v.toggle()
        else:
            raise ValueError(f'Invalid action $x${par2}$x$')    
    def _hdlr_tank_refill(self, par2, params):
        if not par2:
            raise ValueError('Missing refill time parameter')
        self.tank_ctrl.max_refill_time = int (par2)
        self._log.aprint (f'{self._tc.label}Max safe refill time: {self._tc.par}{self._tank_ctrl.max_refill_time} [sec]{self._tc.end}')
    def _hdlr_tank_temp(self, par2, params):
        self._log.aprint (f'{self._tc.cyan}Tank temperature: {self._tc.par}{round (self.tank_ctrl.read_temp(), 2)} [C]{self._tc.end}')
    def _hdlr_tank_trend(self, par2, params):
        self.tank_ctrl.print_trend()
    def _hdlr_tank_all(self, par2, params):
        if not par2:
            raise ValueError('Missing action parameter')
        if par2 == 'on':
            self.tank_ctrl.relay_c.on()
            self.tank_ctrl.relay_p.on()
            self.tank_ctrl.relay_v.on()
        elif par2 == 'off':
            self.tank_ctrl.relay_c.off()
            self.tank_ctrl.relay_p.off()
            self.tank_ctrl.relay_v.off()
        elif par2 == 'toggle':
            self.tank_ctrl.relay_c.toggle()
            self.tank_ctrl.relay_p.toggle()
            self.tank_ctrl.relay_v.toggle()
        else:
            raise ValueError(f'Invalid action $x${par2}$x$')
    def _hdlr_tank_unit (self, par2, params):
        if not par2:
            raise ValueError('Missing unit parameter')
        if par2 in ('c', 'C', 'celsius', 'Celsius'):
            self.tank_ctrl.temp_unit = 'C'
        elif par2 in ('f', 'F', 'fahrenheit', 'Fahrenheit'):
            self.tank_ctrl.temp_unit = 'F'
        elif par2 in ('k', 'K', 'kelvin', 'Kelvin'):
            self.tank_ctrl.temp_unit = 'K'
        else:
            raise ValueError(f'Invalid unit $x${par2}$x$')
    def _hdlr_tank_measure (self, par2, params):
        self.task_manager.add_task(name=par2)
####### TASK COMMANDS ######
    def _hdlr_task_print_reg(self, par2, params):
        self.task_manager.print_task_register()
    def _hdlr_task_restart(self, par2, params):
        self.task_manager.restart_task(task_name=par2)
    def _hdlr_task_run(self, par2, params):
        self.task_manager.add_task(name=par2)
    def _hdlr_task_pause(self, par2, params):
        self.task_manager.pause_task(task_name=par2)
    def _hdlr_task_resume(self, par2, params):
        self.task_manager.resume_task(task_name=par2)
    def _hdlr_task_state(self, par2, params):
        self.task_manager.print_task_status()
    def _hdlr_task_stop(self, par2, params):
        if par2 != 'as_key_cmd':
            self.task_manager.stop_task(task_name=par2)
        else:
            self._log.warning({'msg': f'Task $f${par2}$f$ cannot be stopped', 'src': __name__})
    def _hdlr_task_interval(self, par2, params):
        try:
            self.task_interval (task_name=par2, params=params)
        except (ValueError, NotImplementedError) as ex:
            self._log.error ({'msg': f'Error setting interval for task $f${par2}$f$: $x${ex}$x$'})
####### SYSTEM COMMANDS ######
    def _hdlr_system_debug(self, par2, params):
        if par2:
            self._log.set_level (level=par2)
        else:
            self._log.aprint (f'{self._tc.cyan}Current Debug Level: {self._tc.par}{self._log.get_level()}{self._tc.end} ')
    def _hdlr_system_exit(self, par2=None, params=None):
        self.stop (exc=False)
    def _hdlr_system_state(self, par2=None, params=None):
        self.__sys_state ()
    def _hdlr_system_memory(self, par2, params=None):
        if par2 and par2 == 'clear':
            gc.collect()
        else:
            self._log.aprint (self.help_fncs.get_mem_info(percent=True))
####### UART COMMANDS ######
    def _hdlr_uart_event(self, par2, params=None):
        self._uart.event_simulation (par2)
    def _hdlr_uart_buffer(self, par2, params=None):
        if par2 == 'clear':
            self._uart.clear_buffers ()
        elif par2 == 'rx':
            print (self._uart.get_rx_buffer ())
        elif par2 == 'tx':
            print (self._uart.get_tx_buffer ())
    def _hdlr_uart_msg(self, par2, params=None):
        msg = par2 if par2 else 'Hello from UART server!'
        self._log.aprint (f'Posting: {self._tc.cyan}{msg}{self._tc.end}')
        if self._uart.is_connected:
            self._uart.post ({'msg': msg})
        else:
            self._log.warning ({'msg': '$a$Client not connected$a$', 'src': __name__, 'acc': self._tc.error})
    def _hdlr_uart_state(self, par2=None, params=None):
        self._log.aprint (f'{self._tc.info}UART state:{self._tc.end}')
        self._log.aprint (f'{self._tc.info}------------------------------{self._tc.end}')
        for item in self._uart.uart_state ():
            self._log.aprint (f'{item}')
        val = f'{self._tc.success}ready{self._tc.end}' if self._uart.can_send else f'{self._tc.critical}not ready{self._tc.end}'
        self._log.aprint (f'{self._tc.par}Peer CTS:\t{val}')
    def _hdlr_uart_sim(self, par2, params=None):
        self._log.aprint (f'{self._tc.waiting}Simulating UART thread events...{self._tc.end}')
        self._uart.event_simulation(par2 if par2 else 10)
    def _hdlr_uart_thread(self, par2, params=None):
        if not par2:
            self._hdlr_uart_state()
            return
        if par2 == 'start':
            self._uart.start()
        elif par2 == 'stop':
            self._uart.stop()
        elif par2 == 'pause':
            self._uart.pause_thread ()
            val = f'{self._tc.info}running{self._tc.end}' if not self._uart.thread_is_paused else f'{self._tc.critical}paused{self._tc.end}'
            self._log.info ({'msg': f'{self._tc.dvc}|Core 2 thread|{self._tc.end} {val}'})
        elif par2 == 'resume':
            self._uart.resume_thread ()
            val = f'{self._tc.info}running{self._tc.end}' if not self._uart.thread_is_paused else f'{self._tc.critical}paused{self._tc.end}'
            self._log.info ({'msg': f'{self._tc.dvc}|Core 2 thread|{self._tc.end} {val}'})
        else:
            self._log.warning ({'msg':f'Invalid parameter: $a${par2}$a$; must be either start or stop', 'acc': self._tc.error})
            return
    def _hdlr_uart_encrypt(self, par2, params=None):
        self._fio.write_encrypt (in_fn='plain.txt', out_fn='plain.enc')
        print (f'Encrypted file content: {self._fio.load_file ('plain.enc')}')
    def _hdlr_uart_decrypt(self, par2, params=None):
        self._fio.load_decrypt ('plain.enc')
        print (f'Decrypted file content: {self._fio.load_file ('plain.txt')}')
##### SERVER COMMANDS ######

