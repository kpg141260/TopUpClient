# UART handshake and readiness

Core 1 transports framed bytes and queues log events through the preserved `self.__push_event`. The shared `lib/uart/uart_link.py` state machine runs on Core 0. Both endpoints must use this handshake and the CRC frame format in `uart_protocol.md`.

RTS/CTS represent receive-buffer readiness, using active-low signaling. CTS low permits a frame to be queued; it does not establish a logical connection. The receiver releases RTS when its buffer is drained or cleared. GPIO 4 is not used or allocated for readiness.

The server initiates each connection with a fresh random session token. The following JSON payloads are carried inside checksummed UART frames; the example token is illustrative.

1. Server request:

```json
{"cmd":{"act":"hs","tok":"0011223344556677","data":{"val":"ping","name":"PTCS 1.2.3","to":10}}}
```

2. Client response:

```json
{"rsp":{"act":"hs","tok":"0011223344556677","sta":"ok","data":{"val":"pong","name":"PTCC 1.2.3","to":10}}}
```

3. Server acknowledgement:

```json
{"cmd":{"act":"ready","tok":"0011223344556677"}}
```

`name` contains the device identity supplied by the application entry point. `to` advertises that peer's heartbeat interval as an integer from 1 to 3600 seconds. The challenge/response values come from `config/comms.json`, defaulting to `ping`/`pong`. Responses must match the current session, expected direction, successful status, challenge response, and valid peer metadata. The server marks itself connected after its acknowledgement is accepted into TX; the client requires the matching acknowledgement after its own response was accepted into TX. Lost messages are retransmitted idempotently. Recently retired tokens are retained in a bounded four-session history to reject delayed old requests.

Connection states are `disconnected`, `handshaking`, and `connected`. Each attempt has a deadline derived from `hs_rcv_delay * hs_rcv_max_cnt`; an unready CTS also consumes this budget. Defaults are a 20-second window and three attempts (`hs_max_attempts`), followed by a 30-second cooldown (`hs_interval`). The server then starts a new cycle with a new token. The client waits for a server request rather than initiating its own exchange.

Connected peers send `{"cmd":{"act":"hb","tok":"<current-session>"}}` every `wd_interval` seconds. Valid current-session traffic refreshes receive activity; local timer execution does not. Each side disconnects after silence for the advertised peer interval multiplied by local `max_wd_cnt`. With the supplied configuration, heartbeats are sent every 10 seconds and the silence allowance is 100 seconds. A session-specific `cmd/exit`, worker loss, worker pause, connection-task cancellation, or watchdog expiry clears connected/synchronized flags and peer metadata. Core 0 queues the exit notification; Core 1 only flushes that queued frame during stopping.

`UARTComms.send_line()` rejects application sends while disconnected and adds the current `tok` to connected dictionary envelopes without mutating the caller's dictionary. Incoming application envelopes need that token before they are returned to callers. RTC requests and replies use the same validated receive boundary and the normal receive task on both peers. The asynchronous RTC waiting task never takes receive ownership; all clock work stays on Core 0.

`as_uart_connect`, `as_uart_cmd`, and `as_uart_watchdog` are persistent configurable tasks. Their pause, stop, cancellation, and restart controls remain with the task manager; RTC completion and worker monitoring do not silently resume or restart them. Cancellation/restart operations run on the existing event loop, and shutdown awaits active tasks and control operations before resource destruction. The server's RTC supervisor respects explicitly paused/stopped/cancelled RTC jobs.

Host checks: `python -B -m unittest discover -s tests -p 'test_uart*.py'`. The server's `tests/test_uart_pair.py` additionally requires the sibling `TopUpClient` checkout and exercises both actual transport/connection classes through an in-memory UART cable. These checks do not prove physical GPIO wiring, Pico firmware timing, native Core 1 release, or device memory use.


## RTC protocol v2

Both firmwares need the same RTC protocol. Every `sync` frame carries `v: 2`, a transaction `id`, sample `seq`, and `phase`, in addition to the existing session token and CRC. The server sends `start` with sequence -1. The client sends three `probe` samples (0 through 2); the server answers each with `time`, echoing client send time T1 and supplying server receive/send times T2/T3. The client captures T4 on receipt, selects the lowest-delay sample, and adjusts its current RTC once. Three independent verification probes (3 through 5) follow. The client sends `result`; the server logs and validates it and sends `confirm`. The client only marks itself synchronized after that confirmation. `abort` terminates a failed or cancelled transaction.

Timestamps are integer milliseconds from `time.time_ns()`. The signed server-minus-client offset is `((T2 - T1) + (T3 - T4)) // 2`; positive values advance the client. Delay is measured client monotonic elapsed time minus server processing time `(T3 - T2)`. Samples are rejected if clock elapsed time disagrees with monotonic elapsed time by more than two milliseconds. Verification requires `abs(offset_ms) + ceil(delay_ms / 2) + 2 <= 1000`. The two milliseconds cover integer timestamp/calculation rounding; physical firmware timestamp behavior still needs board validation. Whole-second RTC writes are rounded to the nearest second and checked by fresh probes.

Each transaction uses the configured handshake timeout as its total deadline. Pending frames retry at up to 2.5-second intervals (longer than the maximum round trip compatible with the one-second accuracy bound) with fresh probe/send timestamps. Sequence numbers and echoed T1 values fence stale replies; repeated result/confirmation frames do not write the RTC again. Disconnect resets transaction state. Timeouts, unsupported timestamp APIs, protocol mismatch, RTC write failure, excessive delay, pause, and cancellation leave synchronization unverified and are logged on the server. Failed cycles retry at the configured RTC interval; successful cycles repeat at `freq`, and a new session interrupts that refresh wait. Neither cycle restarts manually stopped UART tasks.
