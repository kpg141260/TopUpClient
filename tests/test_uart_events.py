import ast
import asyncio
from collections import deque
import json
from pathlib import Path
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock


ROOT = Path(__file__).resolve().parents[1]
HELPER = next((ROOT / 'lib/uart').glob('uart_helpers_*.py'))
LEVELS = SimpleNamespace(OFF=0, DEBUG=10, INFO=20, WARNING=30, ERROR=40,
                         CRITICAL=50, TRACE=60, PRINT=70)


def load_method(path, name, namespace):
    tree = ast.parse(path.read_text(encoding='utf-8'))
    method = next(node for node in ast.walk(tree) if
                  isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name)
    # Standalone methods avoid CPython name mangling, matching MicroPython.
    exec(compile(ast.Module(body=[method], type_ignores=[]), str(path), 'exec'), namespace)
    return namespace[name]


class EventBuffer(deque):
    put = deque.append
    get = deque.popleft


class UARTEventTests(unittest.TestCase):
    def setUp(self):
        self.events = EventBuffer()
        self.producer = SimpleNamespace(_ev_buffer=self.events)
        self.push = load_method(HELPER, '__push_event', {})
        self.log = Mock()
        self.log.get_time_stamp.return_value = 'Core 0 timestamp'
        self.register = {'events': {'state': 1, 'intv': 1, 'mx': 1}}

        async def sleep(seconds):
            await asyncio.sleep(0)

        method = load_method(ROOT / 'src/async_handlers.py', 'as_uart_event', {
            'asyncio': SimpleNamespace(sleep=sleep, CancelledError=asyncio.CancelledError),
            'gc': SimpleNamespace(collect=lambda: None), 'task_register': self.register,
        })
        self.consumer = type('Consumer', (), {'as_uart_event': method})()
        self.consumer._ev_buffer = self.events
        self.consumer._log = self.log
        self.consumer._tc = SimpleNamespace(info='<info>', par='<data>', end='<end>')
        self.consumer.dbg_lvls = LEVELS
        self.consumer.as_state = SimpleNamespace(PAUSED=2)
        self.consumer.task_register = self.register
        setattr(self.consumer, '__log_task_started', lambda **kwargs: None)
        setattr(self.consumer, '__log_task_cancelling', lambda **kwargs: None)

    def consume(self):
        async def run():
            task = asyncio.create_task(self.consumer.as_uart_event('events', {}))
            try:
                for _ in range(len(self.events) + 2):
                    await asyncio.sleep(0)
            finally:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        asyncio.run(run())

    def test_enqueue_requires_no_logger_and_preserves_event(self):
        event = {'msg': 'UART error', 'lvl': LEVELS.ERROR, 'ts': 'device timestamp'}
        self.push(self.producer, event)
        self.assertIs(self.events[0], event)
        self.assertEqual(event, {'msg': 'UART error', 'lvl': LEVELS.ERROR, 'ts': 'device timestamp'})
        self.push(SimpleNamespace(_ev_buffer=None), event)

    def test_core0_adds_missing_timestamp_and_preserves_existing_timestamp(self):
        events = [
            {'msg': 'UART active', 'lvl': LEVELS.INFO},
            {'msg': 'UART error', 'lvl': LEVELS.ERROR, 'ts': 'device timestamp'},
        ]
        for event in events:
            self.push(self.producer, event)
        self.assertNotIn('ts', events[0])
        self.consume()
        self.log.get_time_stamp.assert_called_once_with()
        self.log.info.assert_called_once_with({
            'msg': 'UART active', 'lvl': LEVELS.INFO, 'ts': 'Core 0 timestamp',
        })
        self.log.error.assert_called_once_with(events[1])
        self.assertEqual(events[1]['ts'], 'device timestamp')

    def test_transmit_snapshot_is_queued_and_formatted_on_core0(self):
        write = load_method(ROOT / 'lib/uart/uart_full_duplex.py', '_write', {})
        hardware = Mock()
        driver = SimpleNamespace(
            lock=threading.Lock(), can_send=True, cts_pin=SimpleNamespace(value=lambda: 0),
            tx_buffer=bytearray(b'AB....GH'), tx_read_ptr=6, tx_write_ptr=2, buf_size=8,
            _uart=hardware, _push_event=lambda event: self.push(self.producer, event),
        )
        write(driver)
        self.assertEqual(self.events[0], {'uart_tx': b'GHAB'})
        self.assertEqual(b''.join(call.args[0] for call in hardware.write.call_args_list), b'GHAB')
        driver.tx_buffer[:] = b'........'
        self.events.put({'msg': 'Later UART error', 'lvl': LEVELS.ERROR})
        self.consume()
        self.log.debug.assert_called_once_with({
            'msg': "<info>Writing: <data>b'GHAB'<end>",
            'lvl': LEVELS.DEBUG, 'ts': 'Core 0 timestamp',
        })
        self.log.aprint.assert_not_called()
        self.log.error.assert_called_once_with({
            'msg': 'Later UART error', 'lvl': LEVELS.ERROR, 'ts': 'Core 0 timestamp',
        })
        self.assertFalse(self.events)

    def test_paused_consumer_keeps_events_queued(self):
        event = {'msg': 'UART active', 'lvl': LEVELS.INFO}
        self.push(self.producer, event)
        self.register['events']['state'] = 2
        self.consume()
        self.assertEqual(list(self.events), [event])
        self.assertNotIn('ts', event)
        self.log.get_time_stamp.assert_not_called()
        self.register['events']['state'] = 1
        self.consume()
        self.log.info.assert_called_once_with(event)

    def test_rejected_frame_is_logged_on_core0_with_original_bytes(self):
        data = b'bad\xff*0000\n'
        self.push(self.producer, {'uart_rx_error': data})
        self.consume()
        self.log.error.assert_called_once_with({
            'msg': f'UART frame rejected (CRC/format): {data!r}',
            'lvl': LEVELS.ERROR, 'ts': 'Core 0 timestamp',
        })

    def test_worker_lifecycle_and_error_events_require_no_logger(self):
        shared = {'stop': False, 'pause': False}
        errors = []

        def report_progress(error=None):
            if error is None:
                shared['stop'] = True
            else:
                errors.append(error)

        error = OSError('UART read failed')
        worker = load_method(ROOT / 'lib/uart/uart_thread.py', '__main_thread', {
            'shared': shared, 'state_lock': threading.Lock(), 'dl': LEVELS,
            'report_progress': report_progress,
            'time': SimpleNamespace(sleep=lambda seconds: None),
            'gc': SimpleNamespace(mem_free=lambda: 50000, collect=lambda: None),
        })
        uart = Mock(can_send=True)
        uart._read.side_effect = [error, None]
        owner = SimpleNamespace(
            _me='Core 1 UART thread', _tc=SimpleNamespace(success=''),
            _thread_interval=0, _uart=uart,
        )
        setattr(owner, '__push_event', lambda event: self.push(self.producer, event))
        worker(owner)
        self.assertEqual(errors, [error])
        self.assertEqual([event['lvl'] for event in self.events],
                         [LEVELS.INFO, LEVELS.ERROR, LEVELS.INFO])
        self.assertTrue(all('ts' not in event for event in self.events))
        self.consume()
        self.assertEqual(self.log.info.call_count, 2)
        self.assertIn('UART read failed', self.log.error.call_args.args[0]['msg'])
        self.assertIn('mem free: 50000', self.log.error.call_args.args[0]['msg'])

    def test_event_consumer_is_enabled_in_task_configuration(self):
        config = json.loads((ROOT / 'config/async_tasks.json').read_text(encoding='utf-8'))
        self.assertTrue(config['as_uart_event']['run'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
