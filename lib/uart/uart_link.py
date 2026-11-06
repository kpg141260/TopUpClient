__VERSION__ = "0.6.0.2"
# ruff: noqa: RUF100, UP025, UP004, I001, F401, BLE001, S110
import os
import time


class UARTLink:
    """Core 0 connection state; Core 1 only transports framed bytes."""

    def __init__(self, name, server, config, send, event, changed):
        if not isinstance(name, str) or not 0 < len(name.strip()) <= 128:
            raise ValueError('Invalid UART identity')
        self.name, self.server = name, server
        self._send, self._event, self._changed = send, event, changed
        self.poll_interval = float(config.get('hs_rcv_delay', 0.2))
        self.timeout_ms = int(self.poll_interval * int(config.get('hs_rcv_max_cnt', 100)) * 1000)
        self.max_attempts = int(config.get('hs_max_attempts', 3))
        self.cooldown_ms = int(float(config.get('hs_interval', 30)) * 1000)
        self.interval = config.get('wd_interval', 10)
        self.multiplier = int(config.get('max_wd_cnt', 10))
        if (self.poll_interval <= 0 or self.timeout_ms <= 0 or self.max_attempts <= 0
                or self.cooldown_ms < 0 or self.multiplier <= 0
                or type(self.interval) is not int or not 1 <= self.interval <= 3600):
            raise ValueError('Invalid UART handshake timing configuration')
        self._challenge = config.get('challenge_phrase', 'ping')
        self._response = config.get('challenge_response', 'pong')
        self.state = 'disconnected'
        self.session = None
        self.peer_name, self.peer_interval = 'na', None
        self.attempts = 0
        self._next_attempt = time.ticks_ms()
        self._deadline = None
        self._sent = self._ready_pending = False
        self._handshake_sent = False
        self._retired = []
        self._last_rx = self._last_tx = None

    @property
    def is_connected(self):
        return self.state == 'connected'

    def _begin(self, token):
        self._retire_session()
        self.session = token
        self.state = 'handshaking'
        self.attempts = 1
        self._sent = self._ready_pending = False
        self._handshake_sent = False
        self._deadline = time.ticks_add(time.ticks_ms(), self.timeout_ms)
        self._changed()
        if self.max_attempts != 0:
            self._event({'msg': f'UART handshake attempt 1/{self.max_attempts}', 'lvl': 10})
        else:
            self._event({'msg': 'UART handshake attempt 1', 'lvl': 10})

    def _retire_session(self):
        if self.session is not None and self.session not in self._retired:
            self._retired.append(self.session)
            if len(self._retired) > 4:
                self._retired.pop(0)

    def _connected(self):
        if self.is_connected:
            return
        self.state = 'connected'
        self._last_rx = self._last_tx = time.ticks_ms()
        self._changed()
        self._event({'msg': f'UART connected: {self.peer_name}', 'lvl': 20})

    def disconnect(self, reason, notify=False):
        if self.state == 'disconnected':
            return
        token = self.session
        self._retire_session()
        self.state = 'disconnected'
        self.session = None
        self.peer_name, self.peer_interval = 'na', None
        self._next_attempt = time.ticks_add(time.ticks_ms(), self.cooldown_ms)
        self._sent = self._ready_pending = False
        self._handshake_sent = False
        self._changed()
        if notify and token is not None:
            self._send({'cmd': {'act': 'exit', 'tok': token}})
        self._event({'msg': f'UART disconnected: {reason}', 'lvl': 30})

    def poll(self, ready):
        now = time.ticks_ms()
        if self.is_connected:
            if ready and time.ticks_diff(now, self._last_tx) >= self.interval * 1000 and self._send({'cmd': {'act': 'hb', 'tok': self.session}}):
                self._last_tx = now
            return
        if self.state == 'disconnected':
            if not self.server or time.ticks_diff(now, self._next_attempt) < 0:
                return
            self._begin(os.urandom(8).hex())
        if time.ticks_diff(now, self._deadline) >= 0:
            if self.attempts >= self.max_attempts:
                self.disconnect('handshake retry limit reached')
                return
            self.attempts += 1
            if self.max_attempts != 0:
                self._event({'msg': f'UART handshake attempt {self.attempts}/{self.max_attempts}', 'lvl': 10})
            else:
                self._event({'msg': f'UART handshake attempt {self.attempts}', 'lvl': 10})
            self._sent = False
            self._deadline = time.ticks_add(now, self.timeout_ms)
        if not ready:
            return
        if self.server and self._ready_pending:
            if self._send({'cmd': {'act': 'ready', 'tok': self.session}}):
                self._connected()
        elif not self._sent:
            envelope = 'cmd' if self.server else 'rsp'
            message = {'act': 'hs', 'tok': self.session,
                       'data': {'val': self._challenge if self.server else self._response,
                                'name': self.name, 'to': self.interval}}
            if not self.server:
                message['sta'] = 'ok'
            self._sent = bool(self._send({envelope: message}))
            self._handshake_sent = self._handshake_sent or self._sent

    def check_timeout(self):
        if (self.is_connected and time.ticks_diff(time.ticks_ms(), self._last_rx)
                >= self.peer_interval * self.multiplier * 1000):
            self.disconnect('peer watchdog expired')

    def receive(self, message):
        """Consume link control; return False for application messages."""
        if not isinstance(message, dict) or len(message) != 1:
            return True
        envelope = next(iter(message))
        body = message[envelope]
        if not isinstance(body, dict):
            return True
        action = body.get('act')
        if action not in ('hs', 'ready', 'hb', 'exit'):
            if self.is_connected and body.get('tok') == self.session:
                self._last_rx = time.ticks_ms()
                return False
            return True
        token = body.get('tok')
        if (not isinstance(token, str) or len(token) != 16
                or any(char not in '0123456789abcdef' for char in token)):
            return True
        if action == 'hs':
            data = body.get('data')
            if (not isinstance(data, dict) or not isinstance(data.get('name'), str)
                    or not 0 < len(data['name'].strip()) <= 128
                    or type(data.get('to')) is not int or not 1 <= data['to'] <= 3600):
                self._event({'msg': 'UART handshake rejected: invalid peer metadata', 'lvl': 30})
                return True
            if not self.server and envelope == 'cmd' and data.get('val') == self._challenge:
                if token in self._retired:
                    return True
                if (self.session == token and self.peer_interval is not None
                        and (self.peer_name != data['name'].strip() or self.peer_interval != data['to'])):
                    return True
                if self.session != token:
                    if (self.state == 'disconnected'
                            and time.ticks_diff(time.ticks_ms(), self._next_attempt) < 0):
                        return True
                    self._begin(token)
                self.peer_name, self.peer_interval = data['name'].strip(), data['to']
            elif (self.server and envelope == 'rsp' and token == self.session
                    and self._handshake_sent and body.get('sta') == 'ok' and data.get('val') == self._response):
                if self.is_connected:
                    if self.peer_name == data['name'].strip() and self.peer_interval == data['to']:
                        self._send({'cmd': {'act': 'ready', 'tok': token}})
                        self._last_rx = time.ticks_ms()
                else:
                    self.peer_name, self.peer_interval = data['name'].strip(), data['to']
                    self._ready_pending = True
            else:
                self._event({'msg': 'UART handshake rejected: role, challenge, status or session mismatch', 'lvl': 30})
            return True
        if token != self.session or envelope != 'cmd':
            return True
        if action == 'ready' and not self.server and self._handshake_sent:
            self._connected()
        elif action == 'hb' and self.is_connected:
            self._last_rx = time.ticks_ms()
        elif action == 'exit':
            self.disconnect('peer requested exit')
        return True
