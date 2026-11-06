import ast
import asyncio
from collections import deque
from contextlib import redirect_stdout
import gc
import io
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest


ROOT = Path(__file__).resolve().parents[1]


def load_definitions(path, namespace, names):
    tree = ast.parse((ROOT / path).read_text(encoding='utf-8'))
    nodes = [node for node in tree.body
             if isinstance(node, (ast.ClassDef, ast.FunctionDef)) and node.name in names]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(ROOT / path), 'exec'), namespace)


class LoggerFormattingTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads((ROOT / 'config/log_config.json').read_text())
        self.namespace = {
            '__name__': 'logger_test', '__VERSION__': 'test',
            'asyncio': asyncio, 'deque': deque, 'io': io, 'json': json,
            'os': os, 're': re, 'sys': sys, 'time': time, 'MAX_Q': 5,
            'gc': SimpleNamespace(collect=gc.collect, mem_free=lambda: 50000),
            # CPython mangles this module global; MicroPython leaves it unchanged.
            '_FileHandler__fileOperations': None,
        }
        load_definitions('lib/logger/aio.py', self.namespace, ('stdoutHandler', 'stdinHandler'))
        load_definitions('lib/logger/logger.py', self.namespace,
                         ('DbgLevel', 'dbg_lvls', 'Logger', 'DefaultLogHandler'))
        load_definitions('lib/logger/logFormatters.py', self.namespace,
                         ('LogFormatter', 'regex_filters'))
        load_definitions('lib/logger/logHandlers.py', self.namespace,
                         ('FileHandler', 'FileOperations', 'ConsoleHandler', 'get_time_stamp'))
        load_definitions('ptcc_main.py', self.namespace, ('init_logger',))
        self.formatter = self.namespace['LogFormatter']
        self.namespace['dbg_lvls'].setup(self.config['dbg_lvl_map'])

    def event(self):
        return {'msg': 'Pump \x1b[1;38;5;33mready\x1b[0m at $p$42$p$',
                'lvl': 20, 'lbl': 'info', 'ts': '2026-11-06 12:00:00'}

    def test_configured_file_handler_removes_colors_with_and_without_console(self):
        with tempfile.TemporaryDirectory() as directory:
            log_path = Path(directory) / 'event.log'
            config_path = Path(directory) / 'log_config.json'
            self.namespace['_config'] = {'files': {
                'log_config': str(config_path), 'log_file': str(log_path),
            }}
            self.namespace['_file_io'] = SimpleNamespace(
                load_json=lambda path: json.loads(Path(path).read_text()))
            for console in (False, True):
                with self.subTest(console=console):
                    log_path.write_text('')
                    self.config['settings']['enable'].update(file=True, console=console, uart=False)
                    config_path.write_text(json.dumps(self.config))
                    output = io.StringIO()
                    with redirect_stdout(output):
                        logger = self.namespace['init_logger'](self.namespace['_config'])
                        logger.info(self.event())
                    contents = log_path.read_text()
                    self.assertNotIn('\x1b', contents)
                    self.assertNotIn('$p$', contents)
                    self.assertIn('Pump ready at 42', contents)
                    self.assertIn('2026-11-06 12:00:00', contents)
                    if console:
                        self.assertIn(self.config['logColors']['info'], output.getvalue())

    def test_no_color_formatter_strips_preformatted_strings(self):
        formatter = self.formatter(self.config, use_color=False)
        self.assertEqual(formatter.format_output('  Pump \x1b[31mready\x1b[0m\n'),
                         '  Pump ready\n')

    def test_color_setting_from_config_controls_level_colors(self):
        for enabled in (False, True):
            with self.subTest(enabled=enabled):
                self.config['logFormat']['use_color'] = enabled
                formatter = self.formatter(self.config)
                event = self.event()
                event['msg'] = 'Pump ready'
                result = formatter.format_output(event)
                if enabled:
                    self.assertIn(self.config['logColors']['info'], result)
                else:
                    self.assertNotIn('\x1b', result)
                self.assertIn('Pump ready', result)

    def test_explicit_color_setting_overrides_config(self):
        for enabled in (False, True):
            with self.subTest(enabled=enabled):
                self.config['logFormat']['use_color'] = not enabled
                formatter = self.formatter(self.config, use_color=enabled)
                result = formatter.format_output(self.event())
                self.assertEqual('\x1b' in result, enabled)
                self.assertNotIn('$p$', result)


if __name__ == '__main__':
    unittest.main(verbosity=2)
