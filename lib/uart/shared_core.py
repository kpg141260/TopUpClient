__VERSION__ = "0.6.0.4"
# ruff: noqa: RUF100, UP025, UP004, I001, F401, BLE001, S110
# simple shared module used by both cores
import _thread
import time

state_lock = _thread.allocate_lock()
shared = {
    'hb':    0,
    'stop':  False,
    'pause': False,
    'state': 'stopped',
    'last_progress': None,
    'error_count': 0,
    'last_error': None,
    'last_error_time': None,
    'enabled': True
}


def report_progress(error=None):
    error_text = str(error) if error is not None else None
    with state_lock:
        if error is not None:
            shared['error_count'] += 1
            shared['last_error'] = error_text
            shared['last_error_time'] = time.ticks_ms()
            return
        shared['hb'] = ((shared['hb'] + 1) & 0x3FFFFFFF) or 1
        shared['last_progress'] = time.ticks_ms()
        if shared['state'] == 'starting':
            shared['state'] = 'running'
