import ast
import random
from collections import deque
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock


ROOT = Path(__file__).resolve().parents[1]


class UARTClockTests(unittest.TestCase):
    def pair(self, offset=-5000, latency=100, set_error=0):
        self.now = (1 << 30) - 1000
        self.offset = offset
        self.writes = []
        self.messages = deque()
        self.drop = None
        self.latency = latency

        def clock(server):
            return SimpleNamespace(
                time_ns=lambda: (self.now + (0 if server else self.offset)) * 1000000,
                ticks_ms=lambda: self.now % (1 << 30),
                ticks_add=lambda value, delta: (value + delta) % (1 << 30),
                ticks_diff=lambda left, right: (left - right + (1 << 29)) % (1 << 30) - (1 << 29))

        def load(server):
            path = ROOT / 'lib/uart/uart_rtc.py'
            tree = ast.parse(path.read_text())
            namespace = {'time': clock(server)}
            tree.body = [node for node in tree.body if not isinstance(node, ast.Import)]
            exec(compile(tree, str(path), 'exec'), namespace)
            return namespace['UARTClockSync']

        def send(server, message):
            if self.drop != (server, next(iter(message.values()))['phase']):
                delay = self.latency[1 if server else 0] if isinstance(self.latency, tuple) else self.latency
                self.messages.append((self.now + delay, server, message))
            return True

        def apply(stamp):
            self.writes.append(stamp)
            self.offset = ((stamp + 500) // 1000) * 1000 - self.now + set_error

        self.server = load(True)(True, lambda message: send(True, message), Mock(), 20000)
        self.client = load(False)(False, lambda message: send(False, message), Mock(), 20000, apply)

    def step(self):
        self.now += 20
        for endpoint in (self.server, self.client):
            endpoint.poll()
        for _ in range(len(self.messages)):
            due, source, message = self.messages.popleft()
            if due > self.now:
                self.messages.append((due, source, message))
                continue
            (self.client if source else self.server).receive(message)

    def finish(self):
        for _ in range(1500):
            self.step()
            if not self.server.active and not self.client.active and not self.messages:
                return
        self.fail('RTC exchange exceeded its bounded deadline')

    def test_ahead_and_behind_clocks_are_adjusted_once_and_verified(self):
        for offset in (-5000, 7000):
            with self.subTest(offset=offset):
                self.pair(offset)
                self.server.begin()
                self.finish()
                self.assertTrue(self.server.synced)
                self.assertTrue(self.client.synced)
                self.assertLessEqual(abs(self.offset), 1000)
                self.assertEqual(len(self.writes), 1)

    def test_consistent_one_second_set_error_does_not_loop_or_claim_success(self):
        self.pair(set_error=1000)
        self.server.begin()
        self.finish()
        self.assertFalse(self.server.synced)
        self.assertFalse(self.client.synced)
        self.assertEqual(len(self.writes), 1)

    def test_slow_exchange_cannot_claim_one_second_accuracy(self):
        self.pair(latency=1300)
        self.server.begin()
        self.finish()
        self.assertFalse(self.server.synced)
        self.assertFalse(self.client.synced)
        self.assertEqual(self.writes, [])

    def test_asymmetric_delays_are_accounted_for_in_verification(self):
        self.pair(latency=(100, 800))
        self.server.begin()
        self.finish()
        self.assertTrue(self.server.synced)
        self.assertTrue(self.client.synced)
        self.assertLessEqual(abs(self.offset), 1000)
        self.assertEqual(len(self.writes), 1)

    def test_valid_reply_over_one_second_is_not_invalidated_by_retry(self):
        self.pair(latency=600)
        self.server.begin()
        self.finish()
        self.assertTrue(self.server.synced)
        self.assertTrue(self.client.synced)
        self.assertEqual(len(self.writes), 1)

    def test_lost_confirmation_is_retried_without_another_rtc_write(self):
        self.pair()
        self.drop = (True, 'confirm')
        self.server.begin()
        for _ in range(300):
            self.step()
            if self.server.synced:
                break
        self.assertTrue(self.server.synced)
        self.assertFalse(self.client.synced)
        self.drop = None
        self.finish()
        self.assertTrue(self.client.synced)
        self.assertEqual(len(self.writes), 1)

    def test_lost_probe_recovers_with_a_fresh_timestamp(self):
        self.pair()
        self.drop = (False, 'probe')
        self.server.begin()
        for _ in range(50):
            self.step()
        self.drop = None
        self.finish()
        self.assertTrue(self.server.synced)
        self.assertTrue(self.client.synced)
        self.assertEqual(len(self.writes), 1)

    def test_clock_step_during_measurement_invalidates_sample(self):
        self.pair()
        self.server.begin()
        for _ in range(10):
            self.step()
        self.offset += 5000
        self.finish()
        self.assertFalse(self.server.synced)
        self.assertFalse(self.client.synced)
        self.assertEqual(self.writes, [])

    def test_abort_and_stale_transaction_do_not_change_clock(self):
        self.pair()
        self.server.begin()
        start = self.messages[0][2]
        self.server.abort('manual pause')
        self.finish()
        self.client.receive(start)
        self.assertFalse(self.client.active)
        self.assertFalse(self.client.synced)
        self.assertEqual(self.writes, [])

    def test_failed_rtc_write_is_reported_on_both_peers(self):
        self.pair()
        def fail(stamp):
            raise OSError('RTC write failed')
        self.client._set_clock = fail
        self.server.begin()
        self.finish()
        self.assertFalse(self.server.synced)
        self.assertFalse(self.client.synced)
        self.assertIn('RTC write failed', str(self.client._log.warning.call_args_list))
        self.assertIn('RTC write failed', str(self.server._log.warning.call_args_list))

    def test_missing_time_ns_aborts_without_setting_rtc(self):
        self.pair()
        del self.client._now.__func__.__globals__['time'].time_ns
        self.server.begin()
        self.finish()
        self.assertFalse(self.server.synced)
        self.assertFalse(self.client.synced)
        self.assertEqual(self.writes, [])
        self.assertIn('time_ns', str(self.server._log.warning.call_args_list))

    def test_malformed_messages_and_old_protocol_never_write_rtc(self):
        self.pair()
        rng = random.Random(17)
        values = [None, True, -1, 0, 2, 2.0, 'bad', [], {}, 10**30]
        for _ in range(100):
            body = {'act': 'sync', 'v': rng.choice(values), 'id': rng.choice(values),
                    'seq': rng.choice(values), 'phase': rng.choice(values),
                    'data': rng.choice(values)}
            self.client.receive({'cmd': body})
            self.server.receive({'rsp': body})
        self.client.receive({'cmd': {'act': 'sync', 'data': {'sv_ts': 1234}}})
        self.assertEqual(self.writes, [])
        self.assertFalse(self.client.synced)
        self.assertEqual(len(self.messages), 0)

    def test_disconnect_reset_accepts_a_rebooted_server_transaction(self):
        self.pair()
        self.server.begin()
        self.finish()
        self.server.reset()
        self.client.reset()
        self.server._serial = 0
        self.server.begin()
        self.finish()
        self.assertTrue(self.server.synced)
        self.assertTrue(self.client.synced)


if __name__ == '__main__':
    unittest.main(verbosity=2)
