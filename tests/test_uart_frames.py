import ast
import _thread
import binascii
from collections import deque
import json
from pathlib import Path
import random
from types import SimpleNamespace
import unittest
from unittest.mock import Mock


ROOT = Path(__file__).resolve().parents[1]


def frame(payload):
    return payload + ('*%04X\n' % binascii.crc_hqx(payload, 0xFFFF)).encode('ascii')


class UARTFrameTests(unittest.TestCase):
    def setUp(self):
        self.pending = deque()
        self.events = []
        self.hardware = Mock()
        self.hardware.any.side_effect = lambda: bool(self.pending)
        self.hardware.read.side_effect = self.pending.popleft
        self.hardware.write.side_effect = len
        self.now = 0

        def sleep(seconds):
            self.now += int(seconds * 1000)

        self.clock = SimpleNamespace(ticks_ms=lambda: self.now,
                                     ticks_diff=lambda a, b: a - b, sleep=sleep)
        pin = Mock(side_effect=lambda *args: SimpleNamespace(value=Mock(return_value=0)))
        pin.OUT, pin.IN, pin.PULL_UP = 1, 2, 3
        path = ROOT / 'lib/uart/uart_full_duplex.py'
        tree = ast.parse(path.read_text(encoding='utf-8'))
        node = next(node for node in tree.body if isinstance(node, ast.ClassDef))
        namespace = {
            '_thread': _thread, 'json': json, 'time': self.clock, '__VERSION__': 'test',
            'UART': lambda *args: self.hardware, 'Pin': pin,
            'gc': SimpleNamespace(collect=lambda: None),
        }
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), 'exec'), namespace)
        self.uart_class = namespace['FullDuplexUART']
        self.config = {
            'encoding': 'utf-8', 'uart_buf_size': 512, 'crc': True,
            'pin_rts': 3, 'pin_cts': 2, 'uart_id': 0, 'baud_rate': 76800,
            'data_bits': 8, 'parity': 'None', 'stop_bits': 1, 'pin_tx': 0, 'pin_rx': 1,
        }
        self.log = Mock()
        self.colors = SimpleNamespace(waiting='', success='')
        self.uart = self.uart_class(self.log, self.config, self.colors)
        self.uart._push_event = self.events.append

    def feed(self, data):
        self.pending.append(data)
        self.uart._read()

    def transmitted(self):
        self.uart._write()
        data = b''.join(call.args[0] for call in self.hardware.write.call_args_list)
        self.hardware.write.reset_mock()
        return data

    def test_known_crc_vector_and_single_text_trailer_on_every_send_path(self):
        self.assertEqual(self.uart.crc16_ccitt(b'123456789'), 0x29B1)
        for method, value in (
            ('send', b'123456789'), ('send_line', '123456789'),
            ('send_line', b'123456789\n'), ('send_line', bytearray(b'123456789')),
        ):
            with self.subTest(method=method, value=value):
                self.assertTrue(getattr(self.uart, method)(value))
                self.assertEqual(self.transmitted(), b'123456789*29B1\n')
        message = {'msg': 'value*with delimiter', 'line': 'one\ntwo'}
        self.assertTrue(self.uart.send_line(message))
        self.assertEqual(self.transmitted(), frame(json.dumps(message, separators=(',', ':')).encode()))

    def test_fragmented_adjacent_and_wrapped_frames_preserve_exact_payload_bytes(self):
        payload = 'measurement: 23°C*raw'.encode('utf-8') + b'\x00\xff\r'
        data = frame(payload)
        self.uart.rx_read_ptr = self.uart.rx_write_ptr = self.uart.buf_size - 3
        for fragment in data[:-1]:
            self.feed(bytes([fragment]))
            self.assertIsNone(self.uart.read_line())
        self.feed(data[-1:] + frame(b'next'))
        self.assertEqual(self.uart.read_lines(), [payload + b'\n', b'next\n'])

    def test_invalid_frames_are_rejected_before_following_valid_frame(self):
        bad_frames = [
            b'{"act":"exit"}\n', b'{"act":"exit"}*0000\n', b'value*G123\n',
            b'value*+123\n', b'value* 123\n', b'value*12345\n',
            b'value\x00\x01\n', b'value*1234extra\n', b'\n',
        ]
        for bad in bad_frames:
            with self.subTest(frame=bad):
                self.events.clear()
                self.feed(bad + frame(b'valid'))
                self.assertEqual(self.uart.read_line(), b'valid\n')
                self.assertIsNone(self.uart.read_line())
                self.assertEqual(self.events, [{'uart_rx_error': bad}])

    def test_read_validates_once_and_invalid_only_input_times_out(self):
        self.feed(frame(b'valid'))
        self.assertEqual(self.uart.read(timeout_ms=0), b'valid\n')
        self.feed(b'bad*0000\n')
        self.assertIsNone(self.uart.read(timeout_ms=0))
        self.assertEqual(self.events, [{'uart_rx_error': b'bad*0000\n'}])

    def test_frame_capacity_is_checked_before_any_transmit_bytes_are_queued(self):
        self.uart = self.uart_class(self.log, dict(self.config, uart_buf_size=32), self.colors)
        payload = b'a' * (self.uart.buf_size - 1 - 6)
        self.assertTrue(self.uart.send_line(payload))
        before = self.uart.get_buffer_pointers()
        self.assertFalse(self.uart.send_line(b'not enough room'))
        self.assertEqual(self.uart.get_buffer_pointers(), before)
        self.assertEqual(self.transmitted(), frame(payload))
        self.assertFalse(self.uart.send_line(payload + b'a'))
        self.assertEqual(self.transmitted(), b'')

    def test_empty_payload_and_embedded_newline_input(self):
        self.assertTrue(self.uart.send_line(b''))
        self.assertEqual(self.transmitted(), b'*FFFF\n')
        self.feed(b'*FFFF\n')
        self.assertEqual(self.uart.read_line(), b'\n')
        before = self.uart.get_buffer_pointers()
        with self.assertRaises(ValueError):
            self.uart.send_line(b'first\nsecond')
        self.assertEqual(self.uart.get_buffer_pointers(), before)

    def test_checksum_cannot_be_disabled(self):
        with self.assertRaisesRegex(ValueError, 'CRC'):
            self.uart_class(self.log, dict(self.config, crc=False), self.colors)

    def test_readiness_resumes_when_receive_buffer_is_drained_or_cleared(self):
        self.feed(frame(b'a' * 400))
        self.assertEqual(self.uart.rts_pin.value.call_args.args, (1,))
        self.assertEqual(self.uart.read_line(), b'a' * 400 + b'\n')
        self.assertEqual(self.uart.rts_pin.value.call_args.args, (0,))
        self.feed(b'a' * 400)
        self.assertEqual(self.uart.rts_pin.value.call_args.args, (1,))
        self.uart.clear_rx_buffer()
        self.assertEqual(self.uart.rts_pin.value.call_args.args, (0,))

    def test_seeded_byte_payloads_round_trip_and_damaged_checksums_are_rejected(self):
        rng = random.Random(0x2040)
        alphabet = bytes(value for value in range(256) if value != 10)
        for _ in range(100):
            payload = bytes(rng.choice(alphabet) for _ in range(rng.randrange(40)))
            data = frame(payload)
            self.feed(data)
            self.assertEqual(self.uart.read_line(), payload + b'\n')
            corrupted = data[:-2] + (b'0' if data[-2] != ord('0') else b'1') + b'\n'
            self.feed(corrupted)
            self.assertIsNone(self.uart.read_line())


if __name__ == '__main__':
    unittest.main(verbosity=2)
