import ast
import _thread
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock


ROOT = Path(__file__).resolve().parents[1]


def load_class(path, name, namespace):
    tree = ast.parse((ROOT / path).read_text(encoding='utf-8'))
    nodes = [node for node in tree.body if
             isinstance(node, ast.ClassDef) and node.name == name or
             isinstance(node, ast.Assign) and any(
                 isinstance(target, ast.Name) and target.id == '__VERSION__'
                 for target in node.targets)]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(ROOT / path), 'exec'), namespace)
    return namespace[name]


class UARTInitializationTests(unittest.TestCase):
    def setUp(self):
        self.log = Mock()
        self.hardware = Mock()
        self.hardware_factory = Mock(return_value=self.hardware)
        self.colors = SimpleNamespace(waiting='', success='')
        self.gc = SimpleNamespace(collect=lambda: None, mem_free=lambda: 50000)
        self.config = {
            'encoding': 'utf-8', 'uart_buf_size': 512, 'crc': True,
            'pin_rts': 3, 'pin_cts': 2, 'uart_id': 0, 'baud_rate': 76800,
            'data_bits': 8, 'parity': 'None', 'stop_bits': 1,
            'pin_tx': 0, 'pin_rx': 1,
        }
        self.file_io = Mock()
        self.file_io.load_json.side_effect = lambda path: self.config.copy()
        self.events = object()
        namespace = {
            'gc': self.gc, 'UART': self.hardware_factory,
            '_thread': _thread,
        }
        pin = Mock(return_value=Mock())
        pin.OUT, pin.IN, pin.PULL_UP = 1, 2, 3
        namespace['Pin'] = pin
        duplex = load_class('lib/uart/uart_full_duplex.py', 'FullDuplexUART', namespace)
        worker = load_class('lib/uart/uart_thread.py', 'UARTthread', {
            'gc': self.gc, 'FullDuplexUART': duplex,
        })
        helper = load_class('lib/uart/uart_helpers_client.py', 'UARTHelpersClient', {
            'gc': self.gc, 'UARTthread': worker,
        })
        self.uart_class = load_class('lib/uart/uart.py', 'UARTComms', {
            'gc': self.gc, 'UARTHelpersClient': helper,
        })

    def create_uart(self):
        return self.uart_class(
            logger=self.log, file_io=self.file_io, cnf_fn='comms.json',
            tc=self.colors, name='MeasurementClient 1.2.3', event_buffer=self.events,
        )

    def test_processor_preserves_application_identity_and_initializes_uart(self):
        # Execute the caller boundary without starting the tank controller or task engine.
        path = ROOT / 'src/processor.py'
        tree = ast.parse(path.read_text(encoding='utf-8'))
        processor = next(node for node in tree.body if
                         isinstance(node, ast.ClassDef) and node.name == 'Processor')
        constructor = next(node for node in processor.body if
                           isinstance(node, ast.FunctionDef) and node.name == '__init__')
        assignments = {}
        for node in ast.walk(constructor):
            targets = node.targets if isinstance(node, ast.Assign) else (
                [node.target] if isinstance(node, ast.AnnAssign) else [])
            for target in targets:
                if isinstance(target, ast.Attribute) and target.attr in ('_my_info', '_uart'):
                    assignments[target.attr] = node
        owner = SimpleNamespace(_tc=self.colors, _ev_buffer=self.events, _v_prc='9.9.9')
        namespace = {
            'self': owner, 'logger': self.log, 'file_io': self.file_io,
            'tc': self.colors, 'version': object(), 'name': 'MeasurementClient 1.2.3',
            'config': {'self_name': 'DifferentName', 'files': {'comms': 'comms.json'}},
            'UARTComms': self.uart_class,
        }
        nodes = [assignments['_my_info'], assignments['_uart']]
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), 'exec'), namespace)
        self.assertEqual(owner._my_info, 'MeasurementClient 1.2.3')
        self.assertEqual(owner._uart._my_info, owner._my_info)
        self.assertIs(owner._uart._ev_buffer, self.events)
        self.hardware_factory.assert_called_once_with(0)
        self.hardware.init.assert_called_once_with(
            76800, bits=8, parity=None, stop=1, tx=0, rx=1, rts=3, cts=2,
        )
        self.file_io.load_json.assert_called_once_with('comms.json')
        self.log.critical.assert_not_called()
        owner._uart.__destruct__()
        self.hardware.deinit.assert_called_once()

    def test_hardware_initialization_failure_preserves_original_error(self):
        error = OSError('UART unavailable')
        self.hardware.init.side_effect = error
        with self.assertRaises(OSError) as caught:
            self.create_uart()
        self.assertIs(caught.exception, error)
        self.assertTrue(self.log.critical.called)

    def test_configuration_load_failure_preserves_original_error(self):
        error = OSError('Configuration unavailable')
        self.file_io.load_json.side_effect = error
        with self.assertRaises(OSError) as caught:
            self.create_uart()
        self.assertIs(caught.exception, error)
        self.hardware_factory.assert_not_called()


if __name__ == '__main__':
    unittest.main(verbosity=2)
