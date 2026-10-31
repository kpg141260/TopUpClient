__VERSION__ = "0.5.0.1"
# -*- coding: utf-8 -*-
import sys
import select
try:
    import uasyncio as asyncio
except KeyError:
    import asyncio

DEV_MODE = True

###############################################################################
# STDOUT HANDLER
###############################################################################
class stdoutHandler:
    def __init__(self, lock):
        self._lock = lock

    async def awrite(self, message, end='\n'):
        try:
            async with self._lock:
                sys.stdout.write (message + end)
        except OSError as ex:
            if 'TinyUSB' in str(ex):
                sys.stdout.write ('\n')
                pass
        except Exception as ex:
            if DEV_MODE:
                try:
                    sys.stdout.write (f'[awrite error] {ex}')
                except Exception:
                    pass

    def write(self, message, end='\n'):
        try:
            _ = asyncio.current_task()
            asyncio.create_task(self.awrite(message, end))
        except RuntimeError:
            loop = asyncio.new_event_loop()
            loop.run_until_complete(self.awrite(message, end))
            loop.close()
        except Exception:
            try:
                loop = asyncio.get_event_loop()
                loop.run_until_complete(self.awrite(message, end))
            except Exception as e:
                if DEV_MODE:
                    try:
                        sys.stdout.write(f"[write fallback error] {e}\n")
                    except Exception:
                        pass

###############################################################################
# STDIN HANDLER
###############################################################################
class stdinHandler:
    def __init__(self, lock, writer):
        self._lock = lock
        self._writer = writer

    def read(self, prompt=None, end=''):
        try:
            _ = asyncio.current_task()
            return asyncio.create_task(self.aread(prompt, end))
        except RuntimeError:
            loop = asyncio.new_event_loop()
            result = loop.run_until_complete(self.aread(prompt, end))
            loop.close()
            return result

    async def aread(self, prompt=None, end=''):
        async with self._lock:
            return await self.ainput(prompt, end)

    async def ainput(self, prompt=None, end=''):
        buffer = ""
        if prompt:
            await self._writer.write(prompt, end=end)
        async with self._lock:
            while True:
                if sys.stdin in select.select([sys.stdin], [], [], 0)[0]:  # type: ignore
                    char = sys.stdin.read(1)
                    if char in ("\n", "\r"):
                        return buffer
                    else:
                        buffer += char
                await asyncio.sleep(0.1)
