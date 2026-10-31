import sys, gc, asyncio
sys.path.append('/lib/logger')
sys.path.append('/lib/helpers')
sys.path.append('/config')
sys.path.append('/src')
print (f'Current sys path: {sys.path}')
try:
    import uasyncio as asyncio # type: ignore
except:
    import asyncio
from    ansi_esc         import text_colors as tc
from    logger.logger    import Logger
from    logHandlers      import FileHandler, ConsoleHandler
from    logFormatters    import LogFormatter
import  ujson as json # type: ignore

__tc = tc
__logger: Logger   = None

gc.collect()
mem_free_b4 = gc.mem_free()
print (f'{__tc.info}Available memory before loading Logger: {__tc.par}{mem_free_b4} bytes{__tc.end}\n\n')
__logger = Logger (config_fn='/config/config.json', level=None, name='ptcc') # type: ignore
__writer = __logger.getWriter()
gc.collect()
__writer.write (f'{__tc.info}Available memory after Logger initialisation (no handlers or formatters): {__tc.par}{gc.mem_free()} bytes\n\n{__tc.warning}Approx. memory used by basic Logger: {__tc.bred}{mem_free_b4 - gc.mem_free()} bytes{__tc.end}\n\n')
__logger.aprint (f'This is a test message testing the {__tc.success}thread safe {__tc.par}print{__tc.end} function of the logger.')
__logger.basicFormat (lid_value=0)
__logger.info ({'msg': 'This is a simple info message using the Logger DEFAULT handler WITHOUT EVENT ID'})
__logger.basicFormat (lid_value=1)
__logger.error ({'msg': 'This is a complex error message using the Logger DEFAULT handler WITH EVENT ID', 'cls': '<class Testing>', 'src': __name__, 'adr': '127.0.0.1', 'dvc': 'PICO_CLIENT', 'fnc': 'init_logger'})
fh   = FileHandler    (filename='/logs/event.log', truncate=__logger.log_conf['truncate'], name='FH')
ch   = ConsoleHandler (ts_format=__logger.log_fmt['ts_format'], name='CH') # With color
lfnc = LogFormatter   (log_colors=None, log_fmt=__logger.log_fmt, name='LFNC')
lfc  = LogFormatter   (log_colors=__logger.log_colors, log_fmt=__logger.log_fmt, name='LFC')
__logger.addHandler   (ch)
__logger.addHandler   (fh)
ch.addFormatter       (lfc.format_output)
fh.addFormatter       (lfnc.format_output)      # Formats the output string according to the configuration
print (f'\n\n{__tc.info}Available memory after Handlers and formatter have been added: {__tc.par}{gc.mem_free()} bytes\n{__tc.warning}Approx. memory used by full Logger: {__tc.bred}{mem_free_b4 - gc.mem_free()} bytes{__tc.end}\n\n')

__logger.debug ({'msg': 'Logger system successfuly initialised'})
# Logger messages using color handler but no further keyword coloring
__logger.basicFormat (lid_value=0)
__logger.info ({'msg': f'Logger Event ID switched $a$OFF$a$', 'cls': None, 'src': None, 'fnc': None, 'acc': __tc.red})
__logger.debug ({'msg': f'This is a simple DEBUG message using the Logger color handler', 'cls': None, 'src': None, 'fnc': None})
__logger.info ({'msg': f'This is a simple INFO message using the Logger color handler', 'cls': None, 'src': None, 'fnc': None})
__logger.warning ({'msg': f'This is a simple WARNING message using the Logger color handler', 'cls': None, 'src': None, 'fnc': None})
__logger.error ({'msg': f'This is a simple ERROR message using the Logger color handler', 'cls': None, 'src': None, 'fnc': None})
__logger.critical ({'msg': f'This is a simple CRITICAL message using the Logger color handler', 'cls': None, 'src': None, 'fnc': None})
# Logger messages using color handler and keyword coloring
__logger.debug ({'msg': f'This is a $p$complex$p$ DEBUG message using the $a$Logger$a$ $x$color handler$x$', 'cls': '<class Testing>', 'src': __name__, 'adr': '127.0.0.1', 'dvc': 'PICO_CLIENT', 'fnc': 'init_logger', 'acc': __tc.byellow})
__logger.info ({'msg': f'This is a $p$complex$p$ INFO message using the $a$Logger$a$ $x$color handler$x$', 'cls': None, 'src': __name__, 'fnc': 'LoggerTest', 'acc': __tc.par, 'acc': __tc.waiting})
__logger.warning ({'msg': f'This is a $p$complex$p$ warning message using the $a$Logger$a$ $x$color handler$x$', 'cls': None, 'src': __name__, 'fnc': None, 'acc': __tc.par, 'acc': __tc.banner})
__logger.basicFormat (lid_value=1)
__logger.info ({'msg': f'Logger Event ID switched $a$ON$a$', 'cls': None, 'src': None, 'fnc': None, 'acc': __tc.green})
__logger.error ({'msg': f'This is a $p$complex$p$ ERROR message using the $a$Logger$a$ $x$color handler$x$ WITH EVENT ID', 'cls': None, 'src': __name__, 'fnc': 'some function', 'acc': __tc.par, 'acc': __tc.inverse})
__logger.critical ({'msg': f'This is a $p$complex$p$ CRITICAL message using the $a$Logger$a$ $x$color handler$x$ WITH EVENT ID', 'cls': None, 'src': __name__, 'fnc': None, 'acc': __tc.par, 'acc': __tc.stopped})
# Logger messages using color handler but no event/log ID
__logger.basicFormat (lid_value=0)
__logger.info ({'msg': f'Logger Event ID switched $a$OFF$a$', 'cls': None, 'src': None, 'fnc': None, 'acc': __tc.red})
__logger.error ({'msg': f'This is a $p$complex$p$ ERROR message using the $a$Logger$a$ $x$color handler$x$ WITHOUT EVENT ID', 'cls': None, 'src': __name__, 'fnc': 'some function', 'acc': __tc.par, 'acc': __tc.inverse})
__logger.critical ({'msg': f'This is a $p$complex$p$ CRITICAL message using the $a$Logger$a$ $x$color handler$x$ WITHOUT EVENT ID', 'cls': None, 'src': __name__, 'fnc': None, 'acc': __tc.par, 'acc': __tc.stopped})
__logger.basicFormat (lid_value=1)
__logger.info ({'msg': f'Logger Event ID switched $a$ON$a$', 'cls': None, 'src': None, 'fnc': None, 'acc': __tc.green})

try:
    1/0
except Exception as ex:
    __logger.trace ({'exc': ex, 'msg': f'DBZ', 'cls': 'Dummy class','src': None, 'fnc': 'Test', 'adr': '127.0.0.1', 'dvc': 'PICO_CLIENT'})
finally:
    print (f'{__tc.banner}\nThe content of the log file is: {__tc.inverse}')
    with open ('/logs/event.log', 'r') as f:
        print (f.read())
    print (__tc.end)
    __logger.destructor()
    gc.collect()
    print (f'\n\n{__tc.info}Total available memory after exit: {__tc.par}{mem_free_b4} bytes {__tc.end}')
