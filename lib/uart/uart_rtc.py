__VERSION__ = "0.6.0.4"
# ruff: noqa: UP025, UP004, I001, F401, BLE001, S110
import time


class UARTClockSync:
    """Core 0, session-scoped measurement, one RTC adjustment, and verification."""

    def __init__(self, server, send, logger, timeout_ms, set_clock=None):
        self._server, self._send, self._log = server, send, logger
        self._timeout_ms, self._set_clock = timeout_ms, set_clock
        self._serial = 0
        self.reset()

    def reset(self):
        self._id = 0
        self.active = self.synced = False
        self._last = None
        self._seq = -1
        self._best = None
        self._correction = 0

    def _now(self):
        return time.time_ns() // 1000000

    def _message(self, phase, data=None):
        return {'cmd' if self._server else 'rsp': {
            'act': 'sync', 'v': 2, 'id': self._id, 'seq': self._seq,
            'phase': phase, 'data': {} if data is None else data}}

    def _queue(self, phase, data=None):
        self._last = self._message(phase, data)
        self._transmit()

    def _transmit(self):
        body = next(iter(self._last.values()))
        if body['phase'] == 'probe':
            self._t1 = self._now()
            self._started = time.ticks_ms()
            body['data'] = {'t1': self._t1}
        elif body['phase'] == 'time':
            body['data']['t3'] = self._now()
        # Retransmitted packets need independent snapshots and fresh timestamps.
        message = {key: dict(value, data=dict(value['data'])) for key, value in self._last.items()}
        self._send(message)
        # A one-second accuracy bound can still admit almost two seconds of round trip.
        self._retry = time.ticks_add(time.ticks_ms(), min(2500, max(100, self._timeout_ms // 3)))

    def begin(self):
        self.reset()
        self._serial += 1
        self._id = self._serial
        self.active = True
        self._deadline = time.ticks_add(time.ticks_ms(), self._timeout_ms)
        self._queue('start')

    def abort(self, reason, notify=True):
        self.synced = False
        self.active = False
        self._log.warning({'msg': 'UART RTC sync aborted: %s' % reason})
        if notify:
            self._queue('abort', {'reason': reason})
        self._last = None

    def poll(self):
        if not self.active:
            return
        try:
            if time.ticks_diff(time.ticks_ms(), self._deadline) >= 0:
                self.abort('transaction timed out')
            elif time.ticks_diff(time.ticks_ms(), self._retry) >= 0:
                self._transmit()
        except (AttributeError, OSError, ValueError, OverflowError) as ex:
            self.abort(str(ex))

    def receive(self, message):
        if not isinstance(message, dict):
            return False
        body = message.get('rsp' if self._server else 'cmd', {})
        if not isinstance(body, dict):
            return False
        if body.get('act') != 'sync':
            return False
        try:
            if type(body.get('v')) is not int or body['v'] != 2:
                raise ValueError('unsupported RTC protocol; update both peers')
            ident, seq, phase, data = body['id'], body['seq'], body['phase'], body['data']
            if (type(ident) is not int or ident <= 0 or type(seq) is not int
                    or not -1 <= seq <= 5 or not isinstance(data, dict)):
                raise ValueError('invalid RTC transaction metadata')
            if phase == 'start' and not self._server and seq == -1:
                if ident < self._id:
                    return True
                if ident == self._id:
                    if self._last is not None:
                        self._transmit()
                    return True
                self.reset()
                self._id = ident
                self.active = True
                self._deadline = time.ticks_add(time.ticks_ms(), self._timeout_ms)
                self._seq = 0
                self._queue('probe')
            elif ident == self._id:
                if phase == 'abort':
                    reason = data.get('reason', 'peer aborted transaction')
                    self.abort(reason[:160] if isinstance(reason, str) else 'invalid peer abort reason',
                               notify=False)
                elif self._server:
                    self._server_receive(phase, seq, data)
                else:
                    self._client_receive(phase, seq, data)
        except (KeyError, TypeError, ValueError, OverflowError, AttributeError, OSError) as ex:
            self.abort(str(ex), notify=self.active)
        return True

    def _stamp(self, data, key):
        value = data[key]
        if type(value) is not int or not 0 <= value <= 253402300799999:
            raise ValueError('invalid RTC timestamp: %s' % key)
        return value

    def _server_receive(self, phase, seq, data):
        if phase == 'probe' and self.active and seq in (self._seq, self._seq + 1) and seq >= 0:
            t2 = self._now()
            t1 = self._stamp(data, 't1')
            self._seq = seq
            self._queue('time', {'t1': t1, 't2': t2})
        elif phase == 'result' and seq == self._seq:
            if not self.active:
                if self._last is not None:
                    self._transmit()
                return
            offset, delay = data['offset_ms'], data['delay_ms']
            if (type(offset) is not int or type(delay) is not int or delay < 0
                    or type(data['ok']) is not bool or type(data['correction_ms']) is not int):
                raise ValueError('invalid RTC result')
            accepted = data['ok'] and seq == 5 and abs(offset) + (delay + 1) // 2 + 2 <= 1000
            self._log.info({'msg': 'UART RTC result: synchronized=%s, offset_ms=%s, delay_ms=%s, '
                                  'uncertainty_ms=%s, correction_ms=%s' %
                                  (accepted, offset, delay, (delay + 1) // 2 + 2, data['correction_ms'])})
            self.synced = accepted
            self.active = False
            self._queue('confirm', {'ok': accepted})

    def _client_receive(self, phase, seq, data):
        if not self.active:
            return
        if phase == 'confirm' and seq == self._seq and self._last['rsp']['phase'] == 'result':
            if type(data.get('ok')) is not bool:
                raise ValueError('invalid RTC confirmation')
            self.synced = data['ok'] and self._last['rsp']['data']['ok']
            self.active = False
        elif phase == 'time':
            if seq != self._seq or self._last['rsp']['phase'] != 'probe':
                self._transmit()
                return
            t4 = self._now()
            elapsed = time.ticks_diff(time.ticks_ms(), self._started)
            t1, t2, t3 = (self._stamp(data, key) for key in ('t1', 't2', 't3'))
            if t1 != self._t1:
                return
            delay = elapsed - (t3 - t2)
            if t3 < t2 or delay < 0 or abs((t4 - t1) - elapsed) > 2:
                raise ValueError('clock changed during RTC sample')
            offset = ((t2 - t1) + (t3 - t4)) // 2
            if self._best is None or delay < self._best[1]:
                self._best = (offset, delay)
            if seq in (2, 5):
                offset, delay = self._best
                accurate = abs(offset) + (delay + 1) // 2 + 2 <= 1000
                if seq == 5 or (delay + 1) // 2 + 2 > 1000:
                    self._queue('result', {'ok': seq == 5 and accurate,
                                          'offset_ms': offset, 'delay_ms': delay,
                                          'correction_ms': self._correction})
                    return
                self._correction = offset
                self._set_clock(self._now() + offset)
                self._best = None
            self._seq += 1
            self._queue('probe')
