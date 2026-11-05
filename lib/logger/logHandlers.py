__VERSION__ = "0.6.0.12"
# ruff: noqa: RUF100, UP025, UP004, I001, F401, BLE001, S110
# -*- coding: utf-8 -*-
import gc
import os
import time
import ujson as json
from   logger.logger import dbg_lvls
from   collections   import deque
from   uart.uart     import UARTComms
try:
    import usocket as socket
except ImportError:
    try:
        import socket
    except ImportError:
        socket = None

MAX_Q = 4
__fileOperations = None

def get_time_stamp (ts_format) -> str:
    tm = time.gmtime()
    format_map = {
        "%Y": f"{tm[0]:04d}", # Year
        "%m": f"{tm[1]:02d}", # Month
        "%d": f"{tm[2]:02d}", # Day
        "%H": f"{tm[3]:02d}", # Hour
        "%M": f"{tm[4]:02d}", # Minute
        "%S": f"{tm[5]:02d}", # Second
    }
    format = ts_format
    for key, value in format_map.items():
        format = format.replace (key, value)
    return format

###############################################################################
# LOGGER FILE HANDLER
###############################################################################
class FileHandler:
    def __init__ (self, filename: str,truncate: bool=True, max_log_size: int=20000, ts_format: str='%Y-%m-%d %H:%M:%S', name='', level='off'):
        global __fileOperations
        self._name           = name
        self._log_fn         = filename
        self._formatters     = deque ([], MAX_Q)
        self._filters        = deque ([], MAX_Q)
        self._level          = dbg_lvls(level)
        self._ops_ref_cnt    = 0
        # If no object has been created yet, create one
        if __fileOperations is None:
            __fileOperations  = FileOperations (truncate=truncate, max_log_size=max_log_size, ts_format=ts_format)
        # If an object has already been created, use it again
        self._file_ops = __fileOperations
        # Initialize the specific log file
        self._file_ops.init_file (filename)
        self._ops_ref_cnt += 1

    def destructor (self):
        for formatter in self._formatters:
            if hasattr (formatter, 'destructor'):
                formatter.destructor ()
        for filter in self._filters:
            if hasattr (filter, 'destructor'):
                filter.destructor ()
        self._formatters = None
        self._filters = None
        self._name = None
        self._level = None
        self._log_fn = None
        self._file_ops = None
        # __fileOperations object counts the number of instantiations and only destroys itself if count is 0
        # This is to avoid memory leaks
        if self._ops_ref_cnt > 0:
            self._ops_ref_cnt -= 1
        else:
            __fileOperations.destructor ()
        gc.collect()

    def __repr__ (self):
        return f'{self.__class__.__name__} Ver.: ({__VERSION__})'

    def __str__ (self):
        return f'{self.__class__.__name__}'

    def write (self, event_log):
        if isinstance (event_log, dict):
            # del event_log['tgt'] # Remove handler name to avoid recursion
            if self._level <= dbg_lvls.OFF:
                return
            if self._level <= event_log['lvl']:
                if len (self._formatters) == 0:
                    event_str = self._default_formatter (event_log)
                else:
                    for formatter in self._formatters:
                        event_str = formatter (event_log)
                if len (self._filters) > 0:
                    for filter in self._filters:
                        event_str = filter (event_str)
                # Add line break to end of string if not present
                if event_str[len(event_str)-1] != '\n':
                    event_str += '\n'
            elif isinstance (event_log, str):
                event_str = event_log
            else:
                return
            # Remove double spaces
        if event_str:
            self._file_ops.write (event_str, self._log_fn)
            del event_str
        gc.collect()

    def addFormatter (self, formatter):
        if formatter not in self._formatters:
            self._formatters.append (formatter)

    def removeFormatter (self, formatter):
        if formatter in self._formatters:
            self._formatters.remove (formatter)

    def addFilter (self, filter):
        if filter not in self._filters:
            self._filters.append (filter)

    def removeFilter (self, filter):
        if filter in self._filters:
            self._filters.remove (filter)

    def _default_formatter (self, event_log):
        if isinstance (event_log, str):
            return event_log
        elif isinstance (event_log, dict):
            return json.dumps (event_log, separators=(',', ':'))
        else:
            return None

    @property
    def name (self):
        return self._name

###############################################################################
##### FILE OPERATIONS
###############################################################################
class FileOperations:
    def __init__ (self, truncate: bool, max_log_size: int, ts_format: str):
        self._max_log_size   = max_log_size
        self._min_disc_space = 2 * max_log_size
        self._truncate       = truncate
        self._ts_format      = ts_format
        self._ops_ref_cnt    = 0

    def destructor (self):
        if self._ops_ref_cnt > 1:
            self._ops_ref_cnt -= 1
            return

        self._max_log_size = None
        self._min_disc_space = None
        self._truncate = None
        self._ts_format = None
        gc.collect()

    def write (self, event_str, log_fn):
        if event_str is not None and isinstance(event_str, str):
            if self._get_file_size (log_fn) + len (event_str) > self._max_log_size:
                try:
                    self._truncate_log_file (log_fn)
                except OSError:
                    self._delete_file (log_fn)
                    try:
                        self.init_file (log_fn, truncate=True )
                    except Exception as ex:
                        raise OSError (f'{__class__}{__name__}: Log file {log_fn} could not be truncated or created: {ex}')
            #event_str = event_str.replace ('  ', ' ')
            # write to file
            try:
                with open (log_fn, 'a') as f:
                    f.write (event_str)
            except OSError as ex:
                if ex.errno == 28:
                    self._truncate_log_file (log_fn)
                    try:
                        self.init_file (log_fn, truncate=False )
                    except Exception as ex:
                        raise OSError (f'{__class__}{__name__}: Log file {log_fn} could not be truncated or created: {ex}')
            del event_str
        gc.collect()

    def  init_file (self, filename: str, truncate: bool = False):
        _func_name = 'init_file'
        #TODO: correct disc space calculation
        _, free, _ = self._get_disc_space()
        if free < self._min_disc_space / 2:
            self._min_disc_space = round (free / 2, -3)
        # Check available disc space
        if self._min_disc_space < self._max_log_size:
            raise ValueError (f'{__class__}{__name__}.{_func_name} Remaining file system space {free} bytes too low for log file!')
        else:
            try:
                self._create_log_file (filename, truncate)
            except Exception as ex:
                raise OSError (f'{__class__}{__name__}.{_func_name}: {ex}')

        self._ops_ref_cnt += 1

    def _create_log_dir (self, filename: str):
        idx = filename.rfind ('/')
        dir = filename[1:idx]
        try:
            os.mkdir(dir)
        except OSError as ex:
            if ex.errno == 17:
                return
            else:
                raise

    def _create_log_file (self, filename: str, truncate: bool=False):
        # Check if file exists
        try:
            # File exists
            f_info = os.stat (filename)
            if self._truncate or truncate:
                with open (filename, 'w') as f:
                    f.write (f'{get_time_stamp(self._ts_format)} ---------- Log file {filename} truncated ----------\n')
            elif f_info[6] > int (self._max_log_size * 0.5):
                self._truncate_log_file (filename)
            return
        except OSError:
            # Check if dir exists, otherwise create
            self._create_log_dir (filename)
            # File does not exist
            with open (filename, 'a') as f:
                f.write (f'{get_time_stamp(self._ts_format)} ---------- Log file {filename} created ----------\n')

    def _delete_file (self, filename: str):
        os.remove (filename)

    def _truncate_log_file (self, filename: str ):
        try:
            # Get actual size of log file
            f_info = os.stat (filename)
            size = f_info[6]
            if gc.mem_free () < size:
                # Not enough memory to truncate file, so delete it and create a new one
                os.remove (filename)
                self._create_log_file (filename, truncate=True)
            else: # Truncate file
                with open (filename, 'r+') as f:
                    data = f.read ()
                    truncate_length = int (self._max_log_size * 0.5)
                    f.seek  (0)
                    f.write (f'{get_time_stamp(self._ts_format)} ---------- Log file {filename} truncated ----------\n')
                    f.write (data[:truncate_length])
                    f.truncate()
        except Exception as ex:
            raise OSError ( f'{__class__}{__name__}.{'_truncate_log_file'} -> {ex}' )

    def _get_disc_space (self):
        stat = os.statvfs('/')
        size = stat[1] * stat[2]
        free = stat[0] * stat[3]
        used = size - free
        return (size, free, used)

    def _get_file_size (self, filename: str):
        f_info = os.stat (filename)
        return f_info[6]

###############################################################################
# LOGGER UART HANDLER
###############################################################################
class UartHandler:
    def __init__ (self, uart: None = None, ts_format: str='%Y-%m-%d %H:%M:%S.%f', name='', level='off'):
        print (f'{'UartHandler'}.__init__ ({ts_format}, {name}, {level}, {dbg_lvls(level)})')
        self._uart       = uart
        self._ts_format  = ts_format
        self._formatters = deque ([], MAX_Q)
        self._filters    = deque ([], MAX_Q)
        self._name       = name
        self._level      = dbg_lvls(level)
        print (f'UART Handler initialized. Debug level: {self._level}')

    def destructor (self):
        for formatter in self._formatters:
            if hasattr (formatter, 'destructor'):
                formatter.destructor ()
        for filter in self._filters:
            if hasattr (filter, 'destructor'):
                filter.destructor ()
        self._formatters = None
        self._filters = None
        self._name = None
        gc.collect()

    def write (self, event_log):
        if self._uart is None:
            return
        
        if self._level <= dbg_lvls.OFF:
            return
        if len (self._formatters) == 0:
            event_log = self._default_formatter (event_log)
        else:
            for formatter in self._formatters:
                event_log = formatter.format (event_log)
        for filter in self._filters:
            event_log = filter.filter (event_log)
        # IMPORTANT: The UART server has to take care of event compilation and coloration when logging the event, so DO NOT DO IT HERE.
        #            simply forward the raw event to the server
        # The comms uart class provides a buffer of 10 messages. If the buffer is full, the oldest entry will be dropped.
        event = {'log': event_log}
        if isinstance (self._uart, UARTComms):
            self._uart.write (json.dumps (event, separators=(',', ':')).encode('utf-8'))
        else:
            if self._uart.is_connected:
                # NOTE: at this point no changes have been made to the event received
                self._uart.write ({'typ': 'log', 'evt': event_log})

    def addFormatter (self, formatter):
        if formatter not in self._formatters:
            self._formatters.append (formatter)

    def removeFormatter (self, formatter):
        if formatter in self._formatters:
            self._formatters.remove (formatter)

    def addFilter (self, filter):
        if filter not in self._filters:
            self._filters.append (filter)

    def removeFilter (self, filter):
        if filter in self._filters:
            self._filters.remove (filter)
            
    def set_uart (self, uart: UARTComms):
        if not isinstance (uart, UARTComms):
            raise TypeError (f'Expected UARTComms instance, got {type(uart).__name__}')
        self._uart = uart

    @property
    def name (self):
        return self._name

    def _default_formatter (self, event_log) -> str:
        if isinstance (event_log, str):
            return event_log
        elif isinstance (event_log, dict):
            return json.dumps (event_log, separators=(',', ':'))
        else:
            return ''

###############################################################################
# LOGGER CONSOLE HANDLER
###############################################################################
class ConsoleHandler:
    def __init__ (self, writer, ts_format: str='%Y-%m-%d %H:%M:%S.%f', name='', level='off'):
        self._ts_format  = ts_format
        self._formatters = deque ([], MAX_Q)
        self._filters    = deque ([], MAX_Q)
        self._name       = name
        self._writer     = writer
        self._level      = dbg_lvls(level)

    def destructor (self):
        for formatter in self._formatters:
            if hasattr (formatter, 'destructor'):
                formatter.destructor ()
        for filter in self._filters:
            if hasattr (filter, 'destructor'):
                filter.destructor ()
        self._formatters = None
        self._filters = None
        self._name = None
        gc.collect()

    def write (self, event_log):
        if self._level <= dbg_lvls.OFF:
            return
        if isinstance (event_log, dict):
            event_log.pop('tgt')  # Remove handler name to avoid recursion
            event_str: str = ''
            if self._level <= event_log['lvl']:
                event_str: str = ''
                if len (self._formatters) == 0:
                    event_str = self._default_formatter (event_log)
                else:
                    for formatter in self._formatters:
                        event_str = formatter (event_log)
            if len (event_str) > 0:
                for filter in self._filters:
                    event_str = filter (event_str)
            if len (event_str) > 0:
                self._writer.write (event_str)

    def addFormatter (self, formatter):
        if formatter not in self._formatters:
            self._formatters.append (formatter)

    def removeFormatter (self, formatter):
        if formatter in self._formatters:
            self._formatters.remove (formatter)

    def addFilter (self, filter):
        print (f'Adding filter: {filter}')
        if filter not in self._filters:
            self._filters.append (filter)

    def removeFilter (self, filter):
        if filter in self._filters:
            self._filters.remove (filter)

    @property
    def name (self):
        return self._name

    def _default_formatter (self, event_log) -> str:
        if isinstance (event_log, str):
            return event_log
        elif isinstance (event_log, dict):
            return json.dumps (event_log, separators=(',', ':'))
        else:
            return ''

    def flush(self):
        """Dummy flush method to support sys.stdout redirection."""
        return  # ✅ No-op to prevent errors

###############################################################################
# LOGGER SOCKET HANDLER
###############################################################################
class SocketHandler:
    def __init__ (self, host: str, port: int, name='', level='off', timeout=2):
        if socket is None:
            raise ImportError ('SocketHandler requires firmware with socket support')
        self._host       = host
        self._port       = port
        self._name       = name
        self._level      = dbg_lvls(level)
        self._timeout    = timeout
        self._sock       = None
        self._formatters = deque ([], MAX_Q)
        self._filters    = deque ([], MAX_Q)

    def destructor (self):
        self.close()
        for formatter in self._formatters:
            if hasattr (formatter, 'destructor'):
                formatter.destructor ()
        for filter in self._filters:
            if hasattr (filter, 'destructor'):
                filter.destructor ()
        self._formatters = None
        self._filters = None
        gc.collect()

    def close (self):
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
        self._sock = None

    def _connect (self):
        if self._sock:
            return True
        try:
            addr = socket.getaddrinfo(self._host, self._port)[0][-1]
            self._sock = socket.socket()
            self._sock.settimeout(self._timeout)
            self._sock.connect(addr)
            return True
        except Exception:
            self.close()
            return False

    def write (self, event_log):
        if self._level <= dbg_lvls.OFF:
            return

        if isinstance(event_log, dict):
            if self._level > event_log['lvl']:
                return
            event_out = event_log
        else:
            event_out = event_log

        if len(self._formatters) == 0:
            event_str = self._default_formatter(event_out)
        else:
            for formatter in self._formatters:
                event_str = formatter(event_out)

        for filter in self._filters:
            event_str = filter(event_str)

        if not event_str:
            return

        if event_str[-1] != '\n':
            event_str += '\n'

        packet = json.dumps({'typ': 'log', 'evt': event_str}, separators=(',', ':'))

        if self._connect():
            try:
                self._sock.send(packet.encode('utf-8'))
            except Exception:
                self.close()

        gc.collect()

    def addFormatter (self, formatter):
        if formatter not in self._formatters:
            self._formatters.append(formatter)

    def removeFormatter (self, formatter):
        if formatter in self._formatters:
            self._formatters.remove(formatter)

    def addFilter (self, filter):
        if filter not in self._filters:
            self._filters.append(filter)

    def removeFilter (self, filter):
        if filter in self._filters:
            self._filters.remove(filter)

    @property
    def name (self):
        return self._name

    def _default_formatter (self, event_log):
        if isinstance(event_log, str):
            return event_log
        elif isinstance(event_log, dict):
            return json.dumps(event_log, separators=(',', ':'))
        return ''
