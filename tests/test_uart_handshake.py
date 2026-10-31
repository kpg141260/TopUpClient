import ast
from collections import deque
from pathlib import Path
from types import SimpleNamespace
import unittest


ROOT = Path(__file__).resolve().parents[1]


class Clock:
    def __init__(self):
        self.now = 0

    def ticks_ms(self):
        return self.now % (1 << 30)

    def ticks_add(self, ticks, delta):
        return (ticks + delta) % (1 << 30)

    def ticks_diff(self, left, right):
        half = 1 << 29
        return (left - right + half) % (1 << 30) - half


class UARTHandshakeTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.sequence = 0

        def nonce(size):
            self.sequence += 1
            return self.sequence.to_bytes(size, 'big')

        path = ROOT / 'lib/uart/uart_link.py'
        namespace = {'time': self.clock, 'os': SimpleNamespace(urandom=nonce)}
        node = next(n for n in ast.parse(path.read_text()).body if isinstance(n, ast.ClassDef))
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), 'exec'), namespace)
        self.link_class = namespace['UARTLink']
        self.to_server, self.to_client = deque(), deque()
        self.server_events, self.client_events = [], []
        self.server_changes, self.client_changes = [], []
        config = {'hs_rcv_delay': 0.1, 'hs_rcv_max_cnt': 10, 'hs_max_attempts': 3,
                  'hs_interval': 2, 'wd_interval': 1, 'max_wd_cnt': 3}
        self.server = self.link_class('Server 1.2.3', True, config, self.send_server,
                                      self.server_events.append, lambda: self.server_changes.append(self.server.state))
        self.client = self.link_class('Client 4.5.6.7.8', False, config, self.send_client,
                                      self.client_events.append, lambda: self.client_changes.append(self.client.state))
        self.ready = True
        self.drop_response = False
        self.drop_ready = False

    def send_server(self, message):
        if not self.ready:
            return False
        if not (self.drop_ready and message.get('cmd', {}).get('act') == 'ready'):
            self.to_client.append(message)
        return True

    def send_client(self, message):
        if not self.ready:
            return False
        if not (self.drop_response and message.get('rsp', {}).get('act') == 'hs'):
            self.to_server.append(message)
        return True

    def step(self, milliseconds=100):
        self.server.poll(self.ready)
        self.client.poll(self.ready)
        while self.to_client:
            self.client.receive(self.to_client.popleft())
        while self.to_server:
            self.server.receive(self.to_server.popleft())
        self.clock.now += milliseconds

    def connect(self):
        for _ in range(20):
            self.step()
            if self.server.is_connected and self.client.is_connected:
                return
        self.fail('Handshake did not complete')

    def test_matching_request_response_ack_establishes_both_identities(self):
        self.server.poll(True)
        request = self.to_client.popleft()
        self.client.receive(request)
        self.assertFalse(self.client.is_connected)
        self.client.poll(True)
        response = self.to_server.popleft()
        self.assertEqual(response['rsp']['tok'], request['cmd']['tok'])
        self.server.receive(response)
        self.assertFalse(self.server.is_connected)
        self.server.poll(True)
        self.client.receive(self.to_client.popleft())
        self.assertTrue(self.server.is_connected)
        self.assertTrue(self.client.is_connected)
        self.assertEqual(self.server.peer_name, 'Client 4.5.6.7.8')
        self.assertEqual(self.client.peer_name, 'Server 1.2.3')

    def test_lost_response_and_ack_are_retried_without_changing_session(self):
        for drop in ('drop_response', 'drop_ready'):
            with self.subTest(drop=drop):
                self.setUp()
                setattr(self, drop, True)
                for _ in range(5):
                    self.step()
                token = self.server.session
                self.assertFalse(self.client.is_connected)
                setattr(self, drop, False)
                self.connect()
                self.assertEqual(self.server.session, token)
                self.assertEqual(self.client_changes.count('connected'), 1)

    def test_not_ready_and_silent_peer_have_bounded_attempts_and_cooldown(self):
        self.ready = False
        for _ in range(31):
            self.step()
        self.assertEqual(self.server.state, 'disconnected')
        self.assertEqual(self.server.attempts, 3)
        self.assertEqual(len(self.to_client), 0)
        self.ready = True
        for _ in range(10):
            self.step()
        self.assertEqual(self.server.state, 'disconnected')
        for _ in range(20):
            self.step()
            if self.server.is_connected and self.client.is_connected:
                break
        self.assertTrue(self.server.is_connected)
        self.assertTrue(self.client.is_connected)

    def test_wrong_token_status_challenge_and_identity_are_rejected(self):
        self.server.poll(True)
        token = self.server.session
        response = {'act': 'hs', 'tok': token, 'sta': 'ok',
                    'data': {'val': 'pong', 'name': 'Client 1.2', 'to': 1}}
        malformed = [dict(response, tok='0' * 16), dict(response, sta='error'),
                     dict(response, data={'val': 'wrong', 'name': 'Client', 'to': 1}),
                     dict(response, data={'val': 'pong', 'name': '', 'to': 1}),
                     dict(response, data={'val': 'pong', 'name': 'Client', 'to': 0}),
                     dict(response, data={'val': 'pong', 'name': 'Client', 'to': True})]
        for bad in malformed:
            self.server.receive({'rsp': bad})
            self.server.poll(True)
            self.assertFalse(self.server.is_connected)

    def test_ready_backpressure_past_deadline_still_allows_ack_retransmission(self):
        self.server.poll(True)
        self.client.receive(self.to_client.popleft())
        self.client.poll(True)
        self.server.receive(self.to_server.popleft())
        self.clock.now += 1000
        self.server.poll(False)
        self.drop_ready = True
        self.server.poll(True)
        self.assertTrue(self.server.is_connected)
        self.assertFalse(self.client.is_connected)
        self.drop_ready = False
        self.connect()

    def test_exit_expiry_and_new_session_clear_connection_state(self):
        self.connect()
        old_token = self.server.session
        self.server.disconnect('local stop', notify=True)
        self.client.receive(self.to_client.popleft())
        self.assertFalse(self.server.is_connected)
        self.assertFalse(self.client.is_connected)
        self.clock.now += 2000
        self.connect()
        self.assertNotEqual(self.server.session, old_token)
        self.client.receive({'cmd': {'act': 'exit', 'tok': old_token}})
        self.assertTrue(self.client.is_connected)
        self.client.receive({'cmd': {'act': 'hs', 'tok': old_token,
                                     'data': {'val': 'ping', 'name': 'Server 1.2.3', 'to': 1}}})
        self.assertTrue(self.client.is_connected)
        self.assertEqual(self.client.session, self.server.session)
        self.clock.now += 3001
        self.server.check_timeout()
        self.assertFalse(self.server.is_connected)
        self.assertEqual(self.server.peer_name, 'na')

    def test_heartbeats_count_only_for_the_current_session_and_survive_tick_wrap(self):
        self.clock.now = (1 << 30) - 300
        self.connect()
        for _ in range(100):
            self.step()
            self.server.check_timeout()
            self.client.check_timeout()
        self.assertTrue(self.server.is_connected)
        self.assertTrue(self.client.is_connected)
        self.clock.now += 3001
        self.server.receive({'cmd': {'act': 'hb', 'tok': 'f' * 16}})
        self.server.check_timeout()
        self.assertFalse(self.server.is_connected)


if __name__ == '__main__':
    unittest.main(verbosity=2)
