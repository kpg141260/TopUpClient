__VERSION__ = "0.6.0.115"
# ruff: noqa: RUF100, UP025, UP004, I001, F401, BLE001, S110
# -*- coding: utf-8 -*-

import sys
_path = sys.path[:]

# Add the necessary paths to the system path
sys.path.append('/lib/logger')
sys.path.append('/lib/common')
sys.path.append('/lib/uart')
sys.path.append('/config')
sys.path.append('/src')
try:
    try:
        import uasyncio as asyncio
    except ImportError:
        import asyncio
    import gc
    import time
    import machine
    from ansi_esc import text_colors as tc
    from file_io import FILE_IO
    from helpers import helpers
    from logFormatters import LogFormatter
    from logger.logger import Logger
    from logger.logger import dbg_lvls as dl
    from logHandlers import ConsoleHandler, FileHandler, UartHandler
    from version import VersionInfo as version_info
    from processor import Processor
except Exception as ex:
    print ('PTCC startup failed while importing dependencies:')
    sys.print_exception (ex)
    sys.path = _path
    del _path
    # Keep USB connected so the complete traceback can reach the REPL.
    # Imports may have failed before machine or tc became available.
    raise SystemExit

ME       = f'PTCC {__VERSION__}' 
CNF_FILE = '/config/config.json'

_file_io:     FILE_IO | None = FILE_IO (use_encryption=False, seed_file='', shift=0)
_logger:       Logger | None = None
_processor: Processor | None = None
_help_fncs:   helpers | None = helpers ()
_banner: str | None = f'{tc.banner}                                   TopUp Client - {ME}                                    {tc.end}'
_autostart:    bool = True
_autostart_dly: int = 1
_EXIT_DLY:      int = 5
_stopping:     bool = False


def shutdown (hard_reset: bool = True, error: bool = False):
    global _config
    global _logger
    global _processor
    global _stopping
    global _file_io

    if _stopping:
        return
    _stopping = True
    if _logger and isinstance (_logger, Logger):
            _logger.info ( {'msg': f'$a$Executing shutdown request$a$ $p$(hard_reset={hard_reset})$p$ $a$...$a$', 'src': 'ptcc', 'fnc': 'shutdown', 'acc': tc.waiting} )
    # Cleanup the processor object
    if _processor and isinstance (_processor, Processor):
            _processor.stop()
            _processor.destructor()
            _processor = None
            gc.collect()
    if _config and isinstance (_config, dict) and bool (_config.get('showMEm_info')):
        _logger.getMEm_info(percent = True)
        _config.clear()
        _config = None
        
    if _file_io and isinstance (_file_io, FILE_IO):
            _file_io.destructor()
            _file_io = None
            gc.collect()
    # Exit gracefully
    if _EXIT_DLY > 0:
        for _ in range (_EXIT_DLY, -1, -1):
            time.sleep (1)
    # Cleanup the logger
    if isinstance (_logger, Logger):
        _logger.destructor()
        _logger = None
        gc.collect()
    if error:
        print (f'{tc.critical}PTCC {__VERSION__} terminated with error.{tc.end}\n')
    else:
        print (f'{tc.success}PTCC {__VERSION__} terminated gracefully.{tc.end}\n')
    gc.collect()
    
    # Reset the microcontroller
    if not hard_reset:
        machine.soft_reset()
    else:
        machine.reset()
    sys.exit()


def init ():
    global _logger
    global _config
    
    # Initialize the config objecct
    _config = _file_io.load_json (CNF_FILE)
    # Init the logger
    _logger = init_logger(_config)
    
    if _config['get_time']:
        set_time()
        
    # Init the processor
    processor = Processor (
        logger=_logger,
        file_io=_file_io,
        tc=tc,
        config=_config,
        cb_exit=shutdown,
        name=f'{_config.get("self_name")} {__VERSION__}',
        help_fncs=_help_fncs,
        dbg_lvls=dl)

    gc.collect()
    return processor


def init_logger (config) -> Logger:

    try:
        # Load the logger configuration file
        log_config = _file_io.load_json (_config['files']['log_config'])
        
        if isinstance (_config, dict) and _config != {}:
            logger = Logger(
                log_cnf_fn = _config['files']['log_config'],
                level = log_config['tgt_dbg_lvls']['logger'],
                name='ptcc'
            )
            
            lfnc: LogFormatter | None = None
            lfc: LogFormatter  | None = None
            enable = log_config['settings']['enable']
            
            # Construct the log formatters based on the configuration
            if enable.get('console', False) or enable.get('file', False):
                lfnc = LogFormatter(
                    config = log_config,
                    use_color = False,
                    name    = 'lfnc'
                )
            lfc = LogFormatter(
                config = log_config,
                name    = 'lfc'
            )
            
            if enable.get('console', False):
                ch = ConsoleHandler(
                    writer=logger.aWriter(),
                    ts_format=log_config['logFormat']['ts_format'],
                    name='ptcc',
                    level = log_config['tgt_dbg_lvls']['console_handler']
                )
                logger.addHandler(ch)
                ch.addFormatter(lfc.format_output)

            if enable.get('file', False):
                fh = FileHandler(
                    filename=_config['files']['log_file'],
                    truncate=log_config['settings']['truncate'],
                    name='ptcc',
                    level = log_config['tgt_dbg_lvls']['file_handler']
                )
                logger.addHandler(fh)
                fh.addFormatter(lfnc.format_output)
                
            if enable.get('uart', False):
                uh = UartHandler(
                    uart = None,
                    name='ptcc',
                    level = log_config['tgt_dbg_lvls']['uart_handler']
                )
                logger.addHandler(uh)
                uh.addFormatter(lfc.format_output)
                
            return logger
    except Exception as ex:
        print (f'{tc.critical}[critical] {ME} {ex!s}{tc.end}')
        sys.print_exception (ex)
        raise
    finally:
        if log_config:
            log_config = None
        gc.collect()


def set_time ():
    _rtc = machine.RTC()
    t = input (f'{tc.info}Enter date and time in the format {tc.par}yyyy:mm:dd:wd:hh:mm:ss -> {tc.success}')
    time = t.split(':')
    if len (time) == 7:
        _rtc.datetime ((int (time[0]), int (time[1]), int (time[2]), int (time[3]), int (time[4]), int (time[5]), int (time[6]), 0))
        _logger.info ({'msg': f'RTC set to: $a${_rtc.datetime()}$a$', 'acc': tc.success})
    else:
        _logger.warning ({'msg': f'Invalid time entered: $a${input}$a$', 'acc': tc.error})


###############################################################################
#                       Main part starts here                                 #
###############################################################################
#if _name_ == 'main':
"""
    Entry point for the script. Runs the main loop using asyncio.
"""
# Make sure memory has been cleared before starting
gc.collect ()
# Print out the product name and version
print (_banner)
_banner = None

if not _autostart:
    key = input("Enter 's' to start, 'q' to quit...")
    if key == 'q':
        gc.collect()
        machine.soft_reset()
        sys.exit()
else:
    # If autostart then wait for autostart_delay until execution starts
    time.sleep(_autostart_dly)

try:
    # Initialise main objects
    _processor = init()
    # Start the Processor
    if isinstance (_processor, Processor):
        _processor.start ()

except KeyboardInterrupt:
    print(f'{tc.orange}[warning] {ME} Program Interrupted by Ctrl+C{tc.end}')
    shutdown (hard_reset=True)

except Exception as ex:
    print (f'{tc.bred}[critical] {ME} {type (ex)} -> {ex!s}{tc.end}')
    sys.print_exception (ex)
    # Leave the failed startup available for inspection instead of resetting USB.
    raise SystemExit
