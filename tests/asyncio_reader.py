import sys
import uasyncio as asyncio

class AsyncInputBuffer:
    """Manages shared input buffer and synchronization."""
    def __init__(self):
        self.buffer = ""
        self.lock = asyncio.Lock()

    async def add_char(self, char):
        """Append a character to the buffer."""
        async with self.lock:
            if char in ("\n", "\r"):  # Input complete
                data = self.buffer
                self.buffer = ""  # Clear buffer after use
                return data
            else:
                self.buffer += char
        return None  # No complete input yet

    async def get_input(self, prompt=""):
        """Wait until a full input line is available and return it."""
        print(prompt, end="")
        while True:
            async with self.lock:
                if self.buffer:  # Return buffered input when available
                    data = self.buffer
                    self.buffer = ""
                    return data
            await asyncio.sleep(0.1)  # Avoid busy-waiting

class AsyncInputReader:
    """Reads input from sys.stdin and stores it in the shared buffer."""
    def __init__(self, buffer):
        self.buffer = buffer

    async def reader_task(self):
        """Continuously read input character by character."""
        while True:
            char = sys.stdin.read(1)  # Read one character at a time
            result = await self.buffer.add_char(char)
            if result:
                print(f"\n[AsyncInputReader] Received: {result}")

# Usage with Central Task Manager
async def main():
    buffer = AsyncInputBuffer()
    reader = AsyncInputReader(buffer)

    # Task Manager should start this
    asyncio.create_task(reader.reader_task())

    while True:
        user_input = await buffer.get_input("Enter something: ")
        print(f"You typed: {user_input}")
        asyncio.sleep(0.1)

asyncio.run(main())
