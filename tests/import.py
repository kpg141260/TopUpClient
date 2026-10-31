# -*- coding: utf-8 -*-
import sys
__path = sys.path
# Add the necessary paths to the system path
sys.path.append('/lib/logger')
sys.path.append('/lib/common')
sys.path.append('/lib/uart')
sys.path.append('/config')
sys.path.append('/src')
########## CLASS IMPORTS ##########
print ('Starting import..')
import sys
try:
    import uasyncio as asyncio
except:
    import asyncio
try:
    import ujson as json
except:
    import json

import gc, select, sys, re
from   machine          import Pin, PWM, RTC
from   collections      import OrderedDict
try:
    from   tank_controller  import TankController as TankController
    from   helpers          import helpers, FixedSizeFIFO as FIFO
    from   uart.uart        import UARTComms as UARTcomms
    from   task_manager     import TaskManager as TaskManager
    from   async_handlers   import AsyncHandlers
    from   cmd_handlers     import CommandHandlers
    print ('Finished import')
except Exception as ex:
    raise ImportError (f'{ex}')
