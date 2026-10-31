import ast
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock


ROOT = Path(__file__).resolve().parents[1]


class UARTTaskControlTests(unittest.TestCase):
    def manager(self, register, callback):
        async def sleep(seconds):
            await asyncio.sleep(0)

        path = ROOT / 'src/task_manager.py'
        node = next(n for n in ast.parse(path.read_text()).body if isinstance(n, ast.ClassDef))
        namespace = {
            '__file__': str(path),
            'task_register': register, 'Logger': object, 'TextColors': object,
            'asyncio': SimpleNamespace(current_task=asyncio.current_task, create_task=asyncio.create_task,
                sleep=sleep, CancelledError=asyncio.CancelledError,
                run=Mock(side_effect=AssertionError('nested scheduler'))),
            'gc': SimpleNamespace(collect=lambda: None, mem_free=lambda: 50000),
            'sys': SimpleNamespace(print_exception=lambda error: None),
        }
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), 'exec'), namespace)
        cls = namespace['TaskManager']
        colors = SimpleNamespace(success='', waiting='', warning='', critical='', info='', ts='')
        kwargs = {'logger': Mock(), 'tc': colors, 'cb_shutdown': callback}
        if ROOT.name == 'TopUpClient':
            kwargs.update(version=SimpleNamespace(full=lambda path: 'test', compact=lambda path: 'test'),
                          task_register=register)
        return cls(**kwargs)

    def record(self, function):
        return {'fnc': function, 'task': None, 'id': 0, 'state': 0, 'run': True,
                'ro': False, 'cp': True, 'req': True, 'rc': 0, 'mr': 3,
                'intv': 0.1, 'unit': 's', 'mx': 1}

    def test_runtime_cancel_is_awaitable_and_does_not_enter_nested_scheduler(self):
        async def run():
            cleaned = []

            async def child():
                try:
                    await asyncio.Event().wait()
                finally:
                    cleaned.append(True)

            register = {'uart': self.record(None)}
            manager = self.manager(register, lambda: None)
            task = asyncio.create_task(child())
            register['uart'].update(task=task, id=id(task), state=manager.State.RUNNING)
            await asyncio.sleep(0)
            await manager.cancel_task('uart')
            self.assertTrue(task.done())
            self.assertEqual(cleaned, [True])
            self.assertEqual(register['uart']['state'], manager.State.CANCELLED)
            self.assertIsNone(register['uart']['task'])

        asyncio.run(run())

    def test_shutdown_awaits_paused_jobs_and_control_operations_before_callback(self):
        async def run():
            cleaned = []
            callbacks = []

            async def child(name, task_info):
                try:
                    await asyncio.Event().wait()
                finally:
                    cleaned.append(name)

            register = {name: self.record(child) for name in ('paused', 'pending', 'restart')}

            def callback():
                self.assertEqual(set(cleaned), {'paused', 'pending', 'restart'})
                self.assertTrue(pending.done())
                self.assertTrue(restarting.done())
                manager.shutdown()
                manager.destructor()
                callbacks.append(True)

            manager = self.manager(register, callback)
            main = asyncio.create_task(manager.tm_main())
            for _ in range(3):
                await asyncio.sleep(0)
            manager.pause_task('paused')
            pending = manager.cancel_task('pending')
            restarting = manager.restart_task('restart')
            manager.stop()
            await main
            self.assertTrue(pending.done())
            self.assertEqual(callbacks, [True])
            self.assertFalse(manager.is_alive)
            self.assertTrue(all(record['task'] is None for record in register.values()))

        asyncio.run(run())

    def test_persistent_uart_tasks_allow_runtime_pause_stop_and_cancel(self):
        register = json.loads((ROOT / 'config/async_tasks.json').read_text())
        for name in ('as_uart_connect', 'as_uart_cmd', 'as_uart_watchdog'):
            with self.subTest(task=name):
                self.assertTrue(register[name]['run'])
                self.assertFalse(register[name]['ro'])
                self.assertTrue(register[name]['cp'])
                self.assertTrue(register[name]['req'])

    def test_concurrent_restart_cancel_keeps_replacement_registered_and_honors_shutdown(self):
        async def run(stopping):
            started = []
            cleanup_started, release = asyncio.Event(), asyncio.Event()

            async def child(name, task_info):
                started.append(asyncio.current_task())
                try:
                    await asyncio.Event().wait()
                finally:
                    cleanup_started.set()
                    while not release.is_set():
                        try:
                            await release.wait()
                        except asyncio.CancelledError:
                            pass

            register = {'uart': self.record(child)}
            manager = self.manager(register, lambda: None)
            manager.add_task('uart')
            await asyncio.sleep(0)
            restart = asyncio.create_task(manager.restart_task_async('uart'))
            await cleanup_started.wait()
            cancellation = manager.cancel_task('uart')
            await asyncio.sleep(0)
            if stopping:
                manager.stop()
            release.set()
            await asyncio.gather(restart, cancellation)
            await asyncio.sleep(0)
            if stopping:
                self.assertEqual(len(started), 1)
                self.assertIsNone(register['uart']['task'])
            else:
                self.assertEqual(len(started), 2)
                self.assertIs(register['uart']['task'], started[-1])
                self.assertFalse(started[-1].done())
            await manager.shutdown_async()

        for stopping in (False, True):
            with self.subTest(stopping=stopping):
                asyncio.run(run(stopping))


if __name__ == '__main__':
    unittest.main(verbosity=2)
