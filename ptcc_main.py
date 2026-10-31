# -*- coding: utf-8 -*-

from lib.vt_version_object import VersionInfo
from res.vt_version_object import VersionInfo

vi = VersionInfo()
__main_file__  = 'ptcc_main.py'
import sys
__path = sys.path
# Add the necessary paths to the system path
sys.path.append('/lib/logger')
sys.path.append('/lib/common')
sys.path.append('/lib/uart')
sys.path.append('/config')
sys.path.append('/src')
try:
    import uasyncio as asyncio
except:
    import asyncio
try:
    import  machine, gc, time
    from    ansi_esc       import text_colors as tc
    from    logger.logger  import Logger, dbg_lvls as dl
    from    logHandlers    import FileHandler, ConsoleHandler
    from    logFormatters  import LogFormatter
    from    helpers        import helpers
    from    file_io        import FILE_IO as file_io
    from    version        import VersionInfo as version_info
    from    processor      import Processor
except Exception as ex:
    sys.print_exception (ex)
    sys.path = __path
    del __path
    print (f'{tc.critical}PTCS abnormal exit -> Error: {ex}{tc.end}\n')
    machine.reset()

__my_file_name         = 'ptcc_main.py'
__version              = version_info ()
__my_version           = __version.compact (__my_file_name)
__file_io              = file_io (use_encryption=False, seed_file='', shift=0)
__config: dict         = {}
__logger: Logger       = None
__processor: Processor = None
__autostart: bool      = True
__autostart_dly: int   = 1
__config_fn            = '/config/config.json'
__help_fncs            = helpers ()
__EXIT_DLY: int        = 5
__is_shutting_down     = False
__banner: str          = f'{tc.banner}                                     Tank Topup Client - PTCC {__my_version}                                      {tc.end}'

def shutdown (hard_reset: bool = True, error: bool = False):
    _fnc_name = 'shutdown'
    global __config
    global __logger
    global __processor
    global __is_shutting_down
    global __my_version
    global __file_io

    if __is_shutting_down:
        return
    __is_shutting_down = True
    if __logger and isinstance (__logger, Logger):
            __logger.info ( {'msg': f'$a$Executing shutdown request$a$ $p$(hard_reset={hard_reset})$p$ $a$...$a$', 'src': __name__, 'fnc': _fnc_name, 'acc': tc.waiting} )
    # Cleanup the processor object
    if __processor and isinstance (__processor, Processor):
            __processor.stop()
            __processor.__destruct__()
            del __processor
    if __config and isinstance (__config, dict):
            # Print out the memory usage
            if bool (__config.get('show_mem_info')):
                __logger.get_mem_info(percent = True)
                __config.clear()
                del __config
    if __file_io and isinstance (__file_io, file_io):
            __file_io.destructor()
            del __file_io
    # Exit gracefully
    if __EXIT_DLY > 0:
        for _ in range (__EXIT_DLY, -1, -1):
            time.sleep (1)
        # Cleanup the logger
        if isinstance (__logger, Logger):
            __logger.destructor()
            del __logger
    if error:
        print (f'{tc.critical}PTCC {__my_version} terminated with error.{tc.end}\n')
    else:
        print (f'{tc.success}PTCC {__my_version} terminated gracefully.{tc.end}\n')
    gc.collect()
    # Reset the microcontroller
    if not hard_reset:
        machine.soft_reset()
    else:
        machine.reset()
    sys.exit()

def init ():
    # This is the main process
    global __config
    global __logger
    global __version
    global __processor
    global __help_fncs
    _fnc_name = 'init'
    try:
        # Init the logger
        init_logger()
        # Initialise the logger
        __logger.debug ({'msg': f'$p${__my_version}$p$ $a$constructor launched...$a$', 'cls': 'main', 'acc': tc.waiting})
        __config = __file_io.load_json (__config_fn)
        if __config['get_time']:
            set_time()
        # Init the processor
        __processor = Processor (
            logger=__logger,
            version=__version,
            file_io=__file_io,
            tc=tc,
            config=__config,
            cb_exit=shutdown,
            name=f'{__config.get("self_name")} {__version.compact(__main_file__)}',
            help_fncs=__help_fncs,
            dbg_lvls=dl)
        __logger.debug ({'msg': f'$c$__main__$c$ $a$constructor finished$a$', 'src': __name__, 'fnc': None, 'acc': tc.success})
        gc.collect()
    except:
        raise

def init_logger ():
    global __logger
    global __config
    global __file_fn
    global __file_io

    try:
        # Load the logger configuration file
        __config     = __file_io.load_json (__config_fn)
        __log_config = __file_io.load_json (__config['files']['log_config'])
        if isinstance (__config, dict) and __config is not {}:
            __logger = Logger (config_fn = __config['files']['log_config'],
                                level = __log_config['debug_levels']['logger'],
                                name='ptcc'
                                )
            ch = ConsoleHandler (writer=__logger.aWriter(),
                                ts_format=__logger.log_fmt['ts_format'],
                                name='',
                                level = __log_config['debug_levels']['console_handler']
                                )
            __logger.addHandler (ch)
            fh = FileHandler    (filename=__config['files']['log_file'],
                                truncate=__logger.log_conf['truncate'],
                                name='',
                                level = __log_config['debug_levels']['file_handler']
                                )
            __logger.addHandler (fh)
            lfc  = LogFormatter (log_colors=Logger.log_colors,
                                log_fmt=__logger.log_fmt,
                                name='LFC')
            ch.addFormatter     (lfc.format_output)
            lfnc = LogFormatter (log_colors=None,
                                log_fmt=__logger.log_fmt,
                                name='LFNC')
            fh.addFormatter     (lfnc.format_output)      # Formats the output string according to the configuration
            del __log_config
    except Exception as ex:
        print (f'{tc.critical}[critical] [{__name__} {_fnc_name}] {str (ex)}{tc.end}')
        sys.print_exception (ex)
        shutdown (hard_reset=True, error=True)

def set_time ():
    global __config
    global __logger
    __rtc = machine.RTC()
    t = input (f'{tc.info}Enter date and time in the format {tc.par}yyyy:mm:dd:wd:hh:mm:ss -> {tc.success}')
    time = t.split(':')
    if len (time) == 7:
        __rtc.datetime ((int (time[0]), int (time[1]), int (time[2]), int (time[3]), int (time[4]), int (time[5]), int (time[6]), 0))
        __logger.info ({'msg': f'RTC set to: $a${__rtc.datetime()}$a$', 'acc': tc.success})
    else:
        __logger.warning ({'msg': f'Invalid time entered: $a${input}$a$', 'acc': tc.error})

###############################################################################
#                       Main part starts here                                 #
###############################################################################
#if __name__ == 'main':
"""
    Entry point for the script. Runs the main loop using asyncio.
"""
# Make sure memory has been cleared before starting
gc.collect ()
# Print out the product name and version
print (__banner)
del __banner
_fnc_name = 'main'
if not __autostart:
    key = input("Enter 's' to start, 'q' to quit...")
    if key == 'q':
        gc.collect()
        machine.soft_reset()
        sys.exit()
else:
    # If autostart then wait for autostart_delay until execution starts
    time.sleep(__autostart_dly)
try:
    # Initialise main objects
    init()
    __version.destructor ()
    # Start the Processor
    if isinstance (__processor, Processor):
        __processor.start ()

except KeyboardInterrupt:
    print(f'{tc.orange}[warning] [{__name__}{_fnc_name}] Program Interrupted by Ctrl+C{tc.end}')
    shutdown (hard_reset=True)

except Exception as ex:
    print (f'{tc.bred}[critical] [{__name__}.{_fnc_name}] {type (ex)} -> {str (ex)}{tc.end}')
    sys.print_exception (ex)
    shutdown (hard_reset=True)
