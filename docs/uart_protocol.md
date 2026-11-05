# UART frame format

Every frame is `<payload>*<HHHH>\n`. The payload is normally UTF-8 JSON. `HHHH` is exactly four uppercase ASCII hexadecimal digits containing CRC-16/CCITT-FALSE over the exact payload bytes: polynomial `0x1021`, initial value `0xFFFF`, no bit reflection, and final XOR `0x0000`. The checksum excludes the `*` separator and final LF byte. For example, payload `123456789` produces `123456789*29B1\n`.

Payloads may contain `*`, because the separator is identified by its position immediately before the four checksum digits. Literal LF bytes cannot occur inside a payload; JSON strings encode them as `\n`. `FullDuplexUART.send()` and `FullDuplexUART.send_line()` accept one optional trailing LF on their input, append one checksum and one final LF, and reject embedded LF bytes. They enqueue a whole frame or return `False` without changing the transmit queue.

`read_line()`, `read_lines()`, and `read()` validate each complete frame before returning its payload. No filtering or decoding occurs before validation. Returned payloads retain a final LF for compatibility with existing callers; the checksum trailer is removed. Incomplete frames remain buffered. Invalid frames are consumed and discarded, and their original bytes are queued through the existing event helper for error logging on Core 0.

The frame must fit in the configured ring buffer, which reserves one byte to distinguish full from empty. The maximum transmitted payload length is therefore `uart_buf_size - 7` bytes. CRC is required; configuration with `crc: false` fails initialization.

Both server and client must use this format. It is incompatible with the previous binary checksum trailer and unchecked plaintext frames. Update both peers together.
