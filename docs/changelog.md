## 2026-11-06

* Switched `lib/uart/uart_full_duplex.py` to native UART RTS/CTS flow control and removed manual RTS writes. Finite receive-capacity burst tests for both peers are in TopUpServer `tests/test_uart_frames.py`; wiring and pin ownership are documented in TopUpServer `docs/uart_protocol.md`. Physical RTC synchronization remains unverified.

* Fixed UART byte loss in `lib/uart/uart_full_duplex.py`: receive reads are bounded by ring capacity, and unaccepted writes retain their bytes for retry. Shared regression coverage is in TopUpServer `tests/test_uart_frames.py`. Physical RTC synchronization still requires device verification.

# Changes

## 2026-10-31

* Added the shared Core 0 handshake state machine in `lib/uart/uart_link.py`; integrated validated sessions, bounded retries, heartbeats, and disconnect/reconnect state through `lib/uart/uart.py` and `lib/uart/uart_helpers_client.py`. `lib/uart/uart_thread.py` flushes the exit notification queued by Core 0. `lib/uart/uart_full_duplex.py` releases RTS after draining/clearing RX.
* Enabled persistent connection/receive/watchdog jobs in `config/async_tasks.json` and added the retry limit in `config/comms.json`. Corrected task initialization, RTC handling, and task ownership in `src/async_handlers.py`; removed GPIO 4 readiness from `src/processor.py` and report CTS readiness in `src/cmd_handlers.py`. `src/task_manager.py` preserves manual cancellation state and awaits task/control-operation cleanup before destruction.
* Added `tests/test_uart_handshake.py` and `tests/test_uart_task_control.py`; expanded `tests/test_uart_frames.py` and `tests/test_uart_initialization.py`. Documented the sequence in `docs/uart_handshake.md`. The server's paired test requires both checkouts; physical firmware behavior remains unverified.

* Defined the mandatory `payload*HHHH\n` protocol in `docs/uart_protocol.md`. `lib/uart/uart_full_duplex.py` appends one ASCII CRC-16/CCITT-FALSE checksum, preflights whole-frame TX capacity, and validates bytes before returning payloads through any receive method. Invalid frames are discarded and queued for Core 0 logging in `src/async_handlers.py`.
* Added `tests/test_uart_frames.py`, including independent CRC vectors, fragmented/wrapped frames, malformed-input cases, and seeded byte-payload checks. Updated `tests/test_uart_events.py` for rejection logging. Both peers must be updated together; physical hardware remains unverified.

* Preserved `self.__push_event` as an enqueue-only path in `lib/uart/uart_helpers_client.py`. `lib/uart/uart_full_duplex.py` queues immutable transmit snapshots through that helper; `src/async_handlers.py` supplies missing timestamps and formats/outputs diagnostics on Core 0, yielding between events.
* Added `tests/test_uart_events.py` for logger-free enqueueing, deferred timestamp/print handling, immutable transmit snapshots, and consumer pause behavior. Physical Pico/Pico W behavior remains unverified.

* Aligned client UART initialization: `src/processor.py` passes the application identity supplied by the entry point to `UARTComms`; `lib/uart/uart_helpers_client.py` uses the three-argument worker constructor and its own module version for diagnostics; `lib/uart/uart.py` preserves configuration-load errors during constructor cleanup.
* Added host regression checks in `tests/test_uart_initialization.py` for identity propagation, UART initialization/destruction, and original configuration/hardware error propagation. These checks do not start Core 1 or verify physical UART communication.


## RTC synchronization

* Replaced RTC backward-correction retries with protocol v2 measurement, one client RTC adjustment, and independent one-second verification. Added identical `lib/uart/uart_rtc.py` and `tests/test_uart_rtc.py` on server and client; updated role helpers, `lib/uart/uart.py`, and `src/async_handlers.py` for normal receive dispatch, bounded retries, session reset, cancellation, and server-side timing/result diagnostics. The client UART watchdog now checks actual session activity and `config/comms.json` uses a 0.05-second worker interval. Server `tests/test_uart_pair.py` and `tests/async_yield_test.py` cover the new exchange. Both firmwares must be updated together; physical timing remains to be verified.
