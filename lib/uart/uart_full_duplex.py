__VERSION__ = "0.6.0.12"
# ruff: noqa: RUF100, UP025, UP004, I001, F401
# -*- coding: utf-8 -*-
import _thread
import json
import gc
import time
from   machine import UART, Pin

########## FULL DUPLEX UART CLASS ##########
class FullDuplexUART:
    def __init__ (self, logger, cnf, tc):
        self._txt_construct = 'constructor'
        self._txt_destruct  = 'destructor'
        self._txt_finish    = 'finished'
        self._txt_failed    = 'failed'
        self._txt_launch    = 'launched...'
        self._txt_rtc_sync  = 'RTC sync'
        self._txt_success   = 'successfully'
        try:
            self._log          = logger
            self._tc           = tc
            self._log.debug ({'msg': f'$p${__VERSION__}$p$ $a${self._txt_construct} {self._txt_launch}$a$', 'cls': __class__, 'acc': self._tc.waiting})
            self._cnf          = cnf
            self._uart: object = None
            self._encoding     = self._cnf['encoding']
            self.buf_size      = self._cnf['uart_buf_size']
            self._use_crc      = self._cnf['crc']
            self._parity_map   = lambda x: 0 if x == 'Even' else 1 if x == 'Odd' else None
            self.rx_buffer     = bytearray(self.buf_size)
            self.tx_buffer     = bytearray(self.buf_size)
            # Flow control thresholds
            self.rx_high       = int (self.buf_size * 0.75)
            self.rx_low        = int (self.buf_size * 0.5)
            # RTS/CTS pins (manual control)
            self.rts_pin = Pin (self._cnf['pin_rts'], Pin.OUT)
            self.rts_pin.value(1)  # Start with RTS low (NOT ready to receive)
            self.cts_pin = Pin (self._cnf['pin_cts'], Pin.IN, Pin.PULL_UP)
            self.rx_read_ptr   = 0
            self.rx_write_ptr  = 0
            self.tx_read_ptr   = 0
            self.tx_write_ptr  = 0
            self.max_rx_usage  = 0
            self.flow_paused   = False
            self.lock          = _thread.allocate_lock()
            self._init_uart ()
            self._log.debug ({'msg': f'$p${__VERSION__}$p$ $a${self._txt_construct} {self._txt_finish}$a$', 'cls': __class__, 'acc': self._tc.success})
        except (Exception):
            self._log.critical ({'msg': f'$p${__VERSION__}$p$ {self._txt_construct} {self._txt_failed}', 'cls': __class__})
            raise
        finally:
            gc.collect()

    def __destruct__ (self):
        try:
            self._log.debug ({'msg': f'$p${__VERSION__}$p$ $a${self._txt_destruct} {self._txt_launch}$a$', 'cls': __class__, 'acc': self._tc.waiting})
            self._uart.deinit()
            del self._uart
            del self._encoding
            del self.rx_buffer
            del self.tx_buffer
            del self._parity_map
            del self.lock
        finally:
            self._log.debug ({'msg': f'$p${__VERSION__}$p$ $a${self._txt_destruct} {self._txt_finish}$a$', 'cls': __class__, 'acc': self._tc.success})
            del self._txt_construct
            del self._txt_destruct
            del self._txt_finish
            del self._txt_failed
            del self._txt_launch
            del self._txt_rtc_sync
            del self._txt_success
            gc.collect()

    # Initialise the UART
    def _init_uart (self):
        try:
            self._uart = UART(self._cnf['uart_id'])
            # Initialise the UART serial port
            self._uart.init (self._cnf['baud_rate'],  
                             bits=self._cnf['data_bits'], 
                             parity=self._parity_map(self._cnf['parity']), 
                             stop=self._cnf['stop_bits'], 
                             tx=self._cnf['pin_tx'], 
                             rx=self._cnf['pin_rx'], 
                             rts=self._cnf['pin_rts'], 
                             cts=self._cnf['pin_cts'])
            # Start as ready to receive
            self.rts_pin.value(0)
            self._log.debug ({'msg': f'$a$UART {self._cnf['uart_id']} initialised successfully - $a$ Baud: $p${self._cnf['baud_rate']}$p$, ' +  
                             f'DB: $p${self._cnf['data_bits']}$p$, ' +   
                             f'SB: $p${self._cnf['stop_bits']}$p$, ' +   
                             f'P: $p${self._parity_map(self._cnf['parity'])}$p$, ' +   
                             f'TX: $p${self._cnf['pin_tx']}$p$, RX: $p${self._cnf['pin_rx']}$p$, ' + 
                             f'CTS: $p${self._cnf['pin_cts']}$p$, RTS: $p${self._cnf['pin_rts']}$p$', 
                             'acc': self._tc.success}) 
        except Exception as ex:
            self._log.error ( {'msg': f'{ex}', 'cls': __class__, 'src': __name__, 'fnc': 'init_uart'} ) 
            raise

    def _space(self, r, w):
        if w >= r:
            return self.buf_size - (w - r) - 1
        else:
            return (r - w) - 1

    def _usage(self, r, w):
        return self.buf_size - self._space(r, w)

    def _read (self):
        if self._uart.any():
            data = self._uart.read()
            if not data:
                return
            with self.lock:
                for b in data:
                    next_ptr = (self.rx_write_ptr + 1) % self.buf_size
                    if next_ptr == self.rx_read_ptr:
                        # Drop byte
                        continue
                    self.rx_buffer[self.rx_write_ptr] = b
                    self.rx_write_ptr = next_ptr
                usage = self._usage(self.rx_read_ptr, self.rx_write_ptr)
                if usage > self.rx_high:
                    self.rts_pin.value(1)  # stop sender
                elif usage < self.rx_low:
                    self.rts_pin.value(0)  # resume sender

    def _write (self):
        with self.lock:
            if not self.can_send:
                return
            if self.tx_read_ptr == self.tx_write_ptr or self.cts_pin.value() != 0:
                return
            self._log.aprint (f'{self._tc.info}Writing: {self._tc.par}{self.tx_buffer [self.tx_read_ptr:self.tx_write_ptr]}{self._tc.end}')
            while self.tx_read_ptr != self.tx_write_ptr:
                if self.cts_pin.value() != 0:
                    break
                b = self.tx_buffer[self.tx_read_ptr]
                if bytes([b]) == b'':
                    break
                self._uart.write(bytes([b]))
                self.tx_read_ptr = (self.tx_read_ptr + 1) % self.buf_size

    @property
    def can_send(self):
        # CTS LOW means peer is ready
        return self.cts_pin.value() == 0

    def can_receive(self):
        self.rts_pin.value(0)  # Set RTS low (ready to receive)
    def send (self, data: bytes):
        if not self.can_send:
            return False  # don’t queue if peer won’t take it
        with self.lock:
            if self._use_crc:
                data = self.add_crc (data)
            for b in data:
                next_ptr = (self.tx_write_ptr + 1) % self.buf_size
                if next_ptr == self.tx_read_ptr:
                    return False
                self.tx_buffer[self.tx_write_ptr] = b
                self.tx_write_ptr = next_ptr
        return True

    def send_line (self, line):
        """Public: enqueue a line (with newline)"""
        if isinstance (line, dict):
            line = bytearray (json.dumps (line, separators=(',', ':')), self._encoding) 
        elif isinstance (line, str):
            line = bytearray (line, self._encoding)  
        elif isinstance(line, (bytearray, bytes)):
            pass
        else:
            return False
        if line[-1] != ord('\n'):
            line += b'\n'
        if self._use_crc:
            line = self.add_crc (line)
        return self.send (line)

    def read_line (self):
        """Return a full line if available, else None"""
        line = bytearray()
        with self.lock:
            ptr = self.rx_read_ptr
            while ptr != self.rx_write_ptr:
                byte = self.rx_buffer[ptr]
                line.append (byte)
                ptr = (ptr + 1) % self.buf_size
                if byte == ord ('\n') and line:
                    self.rx_read_ptr = ptr
                    return bytes (self.filter_ascii(line))
        return None

    def read_lines (self):
        lines = []
        while True:
            line = self.read_line ()
            if not line:
                break
            lines.append (line)
        return lines

    def read (self, timeout_ms=None):
        t_start = time.ticks_ms() 
        while True:
            line = self.read_line()
            if line:
                if self._use_crc:
                    if self.check_crc (line):
                        clean = line [:-2]
                    else:
                        raise ValueError ('CRC error')
                else:
                    clean = line
                return clean
            if timeout_ms is not None and time.ticks_diff(time.ticks_ms(), t_start) > timeout_ms:
                return None
            time.sleep(0.005)

    def clear_rx_buffer (self):
        with self.lock:
            self.rx_read_ptr = self.rx_write_ptr
    def clear_tx_buffer (self):
        with self.lock:
            self.tx_read_ptr = self.tx_write_ptr

    def clear_buffers (self):
        self.clear_rx_buffer ()
        self.clear_tx_buffer ()

    def get_rx_buffer (self):
        with self.lock:
            return self.rx_buffer

    def get_tx_buffer (self):
        with self.lock:
            return self.tx_buffer

    def get_buffer_pointers (self):
        with self.lock:
            return [self.rx_read_ptr, self.rx_write_ptr, self.tx_read_ptr, self.tx_write_ptr]

    def get_stats (self) -> list[str]:
        with self.lock:
            return [
                f'{self._tc.par}RX Buffer size:\t{self._tc.success}{self.buf_size}{self._tc.end}',
                f'{self._tc.par}RX buffer used:\t{self._tc.success}{self.rx_read_ptr}{self._tc.end}',
                f'{self._tc.par}RX RD pointer:\t{self._tc.success}{self.rx_read_ptr}{self._tc.end}',
                f'{self._tc.par}RX WR pointer:\t{self._tc.success}{self.rx_write_ptr}{self._tc.end}',
                f'{self._tc.par}TX Buffer size:\t{self._tc.success}{self.buf_size}{self._tc.end}',
                f'{self._tc.par}TX buffer used:\t{self._tc.success}{self.tx_read_ptr}{self._tc.end}',
                f'{self._tc.par}TX RD pointer:\t{self._tc.success}{self.tx_read_ptr}{self._tc.end}',
                f'{self._tc.par}TX WR pointer:\t{self._tc.success}{self.tx_write_ptr}{self._tc.end}',
                f'{self._tc.par}CTS is:\t\t{self._tc.info if not self.cts_pin.value() else self._tc.critical}{self.cts_pin.value()}{self._tc.end}{self._tc.end}',
                f'{self._tc.par}RTS is:\t\t{self._tc.info if not self.rts_pin.value() else self._tc.critical}{self.rts_pin.value()}{self._tc.end}{self._tc.end}'
            ]

    def crc16_ccitt (self,data: bytes, poly=0x1021, init=0xFFFF) -> int:
        crc = init
        for byte in data:
            crc ^= byte << 8
            for _ in range(8):
                crc = (crc << 1) ^ poly if (crc & 0x8000) else crc << 1
                crc &= 0xFFFF
        return crc

    def add_crc (self, data: bytes) -> bytes:
        crc = self.crc16_ccitt (data)
        return data + bytes ([crc >> 8, crc & 0xFF])

    def check_crc (self, data: bytes) -> bool:
        if len(data) < 3:
            return False
        crc_received = (data[-2] << 8) | data[-1]
        return self.crc16_ccitt(data[:-2]) == crc_received

    def filter_ascii (self, data: bytes) -> bytes:
        """Filter out non-ASCII characters from the data"""
        return bytes([b for b in data if 0x20 <= b <= 0x7E or b in (0x0A, 0x0D)])
