__VERSION__ = "0.6.0.7"
# ruff: noqa: RUF100, UP025, UP004, I001, F401, RUF012
# -*- coding: utf-8 -*-
import  gc
import  time
import  ujson as json
from    collections   import deque
from    logger.aio    import stdinHandler, stdoutHandler
try:
    import uasyncio as asyncio
except KeyError:
    import asyncio
try:
    from sys import print_exception
except ImportError:  # pragma: no cover
    import traceback
    def print_exception(ex):
        traceback.print_exc()

MAX_Q = 5

class DbgLevel:
    def __init__(self, name, value, description=None):
        self.name = name
        self.value = value
        self.description = description if description is not None else name

    def __repr__(self):      return f"<DbgLevel {self.name}={self.value}>"
    def __str__(self):       return self.name
    def __int__(self):       return self.value
    def __eq__(self, other): return self.value == int(other)
    def __lt__(self, other): return self.value <  int(other)
    def __le__(self, other): return self.value <= int(other)
    def __gt__(self, other): return self.value >  int(other)
    def __ge__(self, other): return self.value >= int(other)
    def __hash__(self):      return hash(self.value)
    def desc (self):         return self.description
class dbg_lvls:
    OFF:        DbgLevel
    DEBUG:      DbgLevel
    INFO:       DbgLevel
    WARNING:    DbgLevel
    ERROR:      DbgLevel
    CRITICAL:   DbgLevel
    TRACE:      DbgLevel
    PRINT:      DbgLevel
    
    _levels:        dict = {}
    _name_to_obj:   dict = {}
    _value_to_obj:  dict = {}

    def __new__ (cls, value):
        """Allow dbg_lvls('DEBUG') style."""
        if isinstance (value, int):
            obj = cls._value_to_obj.get (value)
        else:
            obj = cls._name_to_obj.get (str(value).upper())
        if obj is None:
            raise ValueError(f"Unknown debug level: {value}")
        return obj
    @classmethod
    def get (cls, name):
        """Get level object from name (case-insensitive)."""
        return cls._name_to_obj.get(name.upper(), None)
    @classmethod
    def name (cls, value):
        """Get name from numeric value."""
        obj = cls._value_to_obj.get(value)
        return obj.name if obj else None
    @classmethod
    def setup (cls, levels: dict):
        # Initialise Debug Levels
        # Create named instances like dbg_lvls.DEBUG
        for name, values in levels.items ():
            obj = DbgLevel (name, values[0], values[1])
            setattr (dbg_lvls, name, obj)
            dbg_lvls._name_to_obj[name]       = obj
            dbg_lvls._value_to_obj[values[0]] = obj

class Logger:
###############################################################################
# LOGGER INITIALISATION
###############################################################################
    def __init__(self, log_cnf_fn: str, level=None, name: str='root'):
        Logger.log_config = {}
        print (f'\u001b[38;5;240m{DefaultLogHandler.get_time_stamp()} \u001b[1;38;5;129m[debug] \u001b[38;5;99m<{__class__}> \u001b[1;38;5;129minitialising...\u001b[0m')
        gc.collect ()
        _mem = gc.mem_free()
        self.__shutdown    = False
        Logger.level       = level
        self._name         = name
        self._is_init      = False
        self._handlers     = deque ([], MAX_Q)
        self._lock_logger  = asyncio.Lock()
        self._lock_writer  = asyncio.Lock()
        self._lock_reader  = asyncio.Lock()
        self._log_id       = 1
        try:
            self._writer = stdoutHandler (self._lock_writer)
            self._reader = stdinHandler  (self._lock_reader, self._writer)
            # Check and load logger config file - will raise exception if file not found or invalid,
            # otherwise will populate relevant formatting dictionaries
            self.__load_and_check_log_config_file (log_cnf_fn)
            # Get the debug level descriptions from configuration file
            # Note: This must be done before setting the log level to reflect padding if so desired
            # Set debug level values retrieved from config file
            dbg_lvls.setup (Logger.log_config['dbg_lvl_map'])
            # Set the log level - this can ONLY happen after the debug levels have been setup
            Logger.level      = Logger.log_config.get('tgt_dbg_lvls').get('logger', 'inf') if level is None else dbg_lvls(level)
            self._log_id      = int (Logger.log_config['logFormat'].get('eid_value', 1))
            self._name        = name
            self._def_handler = DefaultLogHandler (format=Logger.log_config['logFormat']['evt_format'], writer=self._writer)
            self._get_ts      = DefaultLogHandler.get_time_stamp
            self._is_init     = True
            self.info ({'msg': f'\u001b[1;38;5;154mLogger initialised.\u001b[38;5;46m Debug level: \u001b[38;5;33m{Logger.level}={int(Logger.level)}\u001b[38;5;46m Memory used: \u001b[38;5;33m{_mem - gc.mem_free()} bytes\u001b[0m', 'eid': 0})
        finally:
            gc.collect()
    def destructor (self):
        try:
            self.debug ({'msg': '__destruct__ launched...', 'cls': __class__, 'src': None, 'fnc': None, 'acc': '\u001b[1;38;5;105m' })
            for handler in self._handlers:
                if hasattr (handler, '__destruct__'):
                    handler.__destruct__()
            self._handlers = None
            if Logger.log_config is not None:
                Logger.log_config.clear()
                Logger.log_config = None
            self._def_handler = None
            self._writer = None
            self._reader = None
            self._lock_writer = None
            self._lock_reader = None
            self._lock_logger = None
        finally:
            print (f'\u001b[38;5;240m{DefaultLogHandler.get_time_stamp()} \u001b[1;38;5;129m[debug] \u001b[38;5;99m<{__class__}> \u001b[1;38;5;129m__destruct__ finished...\u001b[0m')
            gc.collect()
    def __repr__ (self):
        return f'{self.__class__.__name__} Ver.: ({__VERSION__})'
    def __str__ (self):
        return f'{self.__class__.__name__}'
    def __load_and_check_log_config_file (self, log_cnf_fn: str):
        with open (log_cnf_fn, 'r') as f:
            Logger.log_config = json.load (f)
        if 'settings' not in Logger.log_config:
            raise KeyError (f'Logger config file {log_cnf_fn} missing \'settings\' section!')
        if 'tgt_dbg_lvls' not in Logger.log_config:
            raise KeyError (f'Logger config file {log_cnf_fn} missing \'tgt_dbg_lvls\' section!')
        if 'dbg_lvl_map' not in Logger.log_config:
            raise ValueError (f'Logger config file {log_cnf_fn} missing \'dbg_lvl_map\' section!')
        if 'logFormat' not in Logger.log_config:
            raise KeyError (f'Logger config file {log_cnf_fn} missing \'logFormat\' section!')
        if 'logColors' not in Logger.log_config and Logger.log_config['logFormat'].get('use_color', None):
            raise KeyError (f'Logger config file {log_cnf_fn} missing \'logColors\' section!')
        if 'evt_tag_map' not in Logger.log_config:
            raise KeyError (f'Logger config file {log_cnf_fn} missing \'evt_tag_map\' section!')
        if 'filters' not in Logger.log_config:
            raise KeyError (f'Logger config file {log_cnf_fn} missing \'filters\' section!')
###############################################################################
# LOGGER MAIN METHODS
###############################################################################
    async def _async_log (self, event_log):
        async with self._lock_logger:
            # If there are no handlers use default handler, which will direct log to console
            if len(self._handlers) == 0:
                self._def_handler.write (event_log)
            else:
                for handler in self._handlers:
                    # Filter out handlers that do not match the name
                    # This is useful when using multiple instances of the same handler
                    if event_log.get('tgt', '') == '' or handler.name == event_log.get('tgt'):
                        handler.write (event_log)
    def _log (self, event_log):
        # Sync log handler
        # If there are no handlers use default handler, which will direct log to console
        if len(self._handlers) == 0:
            self._def_handler.write (event_log)
        else:
            for handler in self._handlers:
                if isinstance (event_log, dict):
                    # Filter out handlers that do not match the name
                    # This is useful when using multiple instances of the same handler
                    if event_log.get('tgt', '') == '' or handler.name == event_log.get('tgt'):
                        handler.write (event_log)
                else:
                    handler.write (event_log)
    def log (self, event_log, level: int):
        """Wrapper function to allow logging from both async and sync contexts"""
        # Set the log level and label
        # If the event_log is a dictionary, format accordingly 
        if isinstance (event_log, dict):
            event_log['lvl'] = level
            event_log['lbl'] = dbg_lvls(level).desc()
            
            # Increment log id only if the initial value is > 0 and the eid_format is > 0
            # This ensures that changes to basicFormat are reflected in the log
            event_log['eid'] = self._log_id
            self._log_id += 1
            if self._log_id > 999999:
                self._log_id = 1
            # Ensure the event_log has all the required fields
            if 'tgt' not in event_log:
                event_log['tgt'] = ''
        else:
            # Process event_log string
            event_log = f'{self.get_time_stamp()} [{dbg_lvls(level).desc()}] {event_log}'
        if not Logger.__shutdown:
            # Use the async log function
            try:
                _ = asyncio.current_task()
                asyncio.create_task(self._async_log (event_log))  # Run in existing event loop
            except RuntimeError:
                # Use the sync log function
                self._log (event_log)
            
###############################################################################
# LOGGER PUBLIC LOG METHODS
###############################################################################
    def debug (self, event_log):
        if Logger.level == dbg_lvls.OFF:
            return
        if Logger.level <= dbg_lvls.DEBUG:
            self.log (event_log, int (dbg_lvls.DEBUG))
    def info (self, event_log):
        if Logger.level == dbg_lvls.OFF:
            return
        if Logger.level <= dbg_lvls.INFO:
            self.log (event_log, int (dbg_lvls.INFO))
    def warning (self, event_log):
        if Logger.level == dbg_lvls.OFF:
            return
        if Logger.level <= dbg_lvls.WARNING:
            self.log (event_log, int (dbg_lvls.WARNING))
    def error (self, event_log):
        if Logger.level == dbg_lvls.OFF:
            return
        if Logger.level <= dbg_lvls.ERROR:
            self.log (event_log, int (dbg_lvls.ERROR))
    def critical (self, event_log):
        if Logger.level == dbg_lvls.OFF:
            return
        if Logger.level <= dbg_lvls.CRITICAL:
            self.log (event_log, int (dbg_lvls.CRITICAL))
    def trace (self, event_log):
        if Logger.level == dbg_lvls.OFF:
            return
        self.log (event_log, int (dbg_lvls.TRACE))
    def aprint (self, message, end='\n'):
        if isinstance (message, dict):
            message = message['msg']
        elif isinstance (message, str):
            pass
        else:
            message = 'unsupported message type'
        self._writer.write (message, end) #type: ignore
    def log_event (self, lvl, event):
        if lvl == dbg_lvls.OFF:
            return

        log_methods = {
            dbg_lvls.PRINT:    self.aprint,
            dbg_lvls.TRACE:    self.trace,
            dbg_lvls.DEBUG:    self.debug,
            dbg_lvls.INFO:     self.info,
            dbg_lvls.WARNING:  self.warning,
            dbg_lvls.ERROR:    self.error,
            dbg_lvls.CRITICAL: self.critical,
        }

        log_fnc = log_methods.get(lvl)
        if log_fnc:
            log_fnc (event)
        else:
            raise ValueError(f'Log level \'{lvl}\' not implemented in Class {__class__}')

###############################################################################
# LOGGER PUBLIC HELPER METHODS
###############################################################################
    def addHandler (self, handler):
        if handler not in self._handlers:
            if not hasattr (handler, 'write') or not callable (handler.write) or not hasattr (handler, 'name'):
                raise AttributeError (f'{__class__.__name__} handler object must have \'write\' and \'name\' attributes!')
            self._handlers.append (handler)
            if hasattr (handler, 'setLock'):
                handler.setLock (self._lock_writer)
            if hasattr (handler, 'setWriter'):
                handler.setWriter (self._writer)
    def removeHandler (self, handler):
        if handler in self._handlers:
            self._handlers.remove (handler)
    def get_level (self):
        return Logger.level
    def set_level (self, level):
        Logger.level = dbg_lvls (level)
        self.info ({'msg': f'Log level changed to: $p${[Logger.level]}={int (Logger.level)}$p$'})
    def getLogger (self):
        return self
    def aWriter (self):
        return self._writer
    def aReader (self):
        return self._reader
    def reader_lock (self):
        return self._lock_reader
    def writer_lock (self):
        return self._lock_writer

###############################################################################
# LOGGER CLASS METHODS
###############################################################################
    @classmethod
    def basicColors (self, **kwargs):
        for key, value in kwargs.items():
            if isinstance (value, dict):
                Logger.log_config['logColors'] = {k: v for k, v in value.items().copy()}
            else:
                if key in Logger.log_config['logColors']:
                    Logger.log_config['logColors'][key] = value
                else:
                    raise AttributeError (f'basicColors has no attribute {key}')
    # @classmethod
    def basicFormat (self, **kwargs):
        for key, value in kwargs.items():
            if isinstance (value, dict):
                Logger.log_config['logFormat'] = {k: v for k, v in value.items().copy()}
            else:
                if key in Logger.log_config['logFormat']:
                    Logger.log_config['logFormat'][key] = value
                else:
                    raise AttributeError (f'basicFormat has no attribute {key}')
    @classmethod
    def debugLevelMap (self, **kwargs):
        for key, value in kwargs.items():
            if isinstance (value, dict):
                Logger.log_config['dbg_lvl_map'] = {int(k): v for k, v in value.items()}
            else:
                if int(key) in Logger.log_config['dbg_lvl_map']:
                    Logger.log_config['dbg_lvl_map'][int(key)] = value
                else:
                    raise AttributeError (f'basicConfig has no attribute {key}')
    @classmethod
    def shutdownMode (self):
        self.__shutdown = True
    def get_time_stamp (self):
        return self._get_ts()
    @staticmethod
    def pad_string (s, length):
        padding = length - len(s)
        if padding % 2 == 0:
            return ' ' * (padding // 2) + s + ' ' * (padding // 2)
        else:
            return ' ' * ((padding // 2) + 1) + s + ' ' * (padding // 2)
    
###############################################################################
# LOGGER DEFAULT HANDLER
###############################################################################
class DefaultLogHandler:
    def __init__ (self, format: str, writer, name: str=''):
        self._format = format
        self._writer = writer
        self._name   = name

    def __str__ (self):
        return self._name

    def write (self, event_log):
        ts = self.get_time_stamp()
        if isinstance (event_log, str):
            event_log = f'{ts} {event_log}'
            self._writer.write (event_log)
        elif isinstance (event_log, dict):
            event_log['ts'] = ts
            # Override sys.stdout to use this handler
            self._writer.write (self._formatter (event_log))

    def _formatter (self, event):
        # If the event is a string return
        if isinstance (event, str):
            return event
        # If the event is a dictionary proceed
        if not isinstance (event, dict):
            raise TypeError (f'{__class__} {__name__} event must be a string or dictionary')
        format_str = self._format
        if int (event['lvl']) == dbg_lvls.TRACE:
            print_exception (event['exc'])
            event['msg'] = 'Trace output above'
        format_map = {
            'adr': f'{event.get('adr', '')}',           # Event source IP
            'cls': f'{event.get('cls', '')}',           # Event source Class
            'dvc': f'{event.get('dvc', '')}',           # Event source Device
            'fnc': f'{event.get('fnc', '')}',           # Event source Function
            'eid': f'{event.get('eid', '')}',           # Event source ID
            'pid': f'{event.get('pid', '')}',           # Event source PID
            'mem': f'{event.get('mem', '')}',           # Event source Memory
            'msg': f'{event.get('msg', 'no message')}', # Event source Message
            'src': f'{event.get('src', '')}',           # Event source Timestamp
            'ts':  f'{event.get('ts',  '')}',           # Event source Source File
            'lbl': f'{event.get('lbl', '')}',           # Debug level text
        }
        event['lbl'] = f'[{event['lbl']}]'
        for key, value in format_map.items():
            if key in event:
                if event[key] == '' or event[key] is None:
                    format_str = format_str.replace (f'%{key}%', '')
                else:
                    if key == 'eid':
                        if int (value) > 0:
                            value = f'{int (value):06d}'
                        else:
                            value = ''
                    format_str = format_str.replace (f'%{key}%', value)
            else:
                format_str = format_str.replace (f'%{key}%', '')
                
        cleaned = format_str.strip()
        while '  ' in cleaned:
            cleaned = cleaned.replace('  ', ' ')
        return cleaned

    @classmethod
    def get_time_stamp (cls) -> str:
        tm = time.gmtime()
        return f'{tm[0]:04d}-{tm[1]:02d}-{tm[2]:02d} {tm[3]:02d}:{tm[4]:02d}:{tm[5]:02d}'

