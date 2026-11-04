__VERSION__ = "0.6.0.9"
# ruff: noqa: RUF100, UP025, UP004, I001, F401, BLE001, E722
# -*- coding: utf-8 -*-
try:
    import uasyncio as asyncio
except:
    import asyncio
import gc, time, sys
from typing import ClassVar
from logger.logger import Logger


class TaskManager:
    class State:
        DISABLED   = 0
        RUNNING    = 1
        PAUSED     = 2
        COMPLETED  = 3
        CANCELLED  = 4
        STOPPED    = 5
        RECOVERING = 6
        FAILED     = 7
        UNKNOWN    = 8
        SCHEDULED  = 9

    S2T: ClassVar[dict[int, str]] = {
        0: 'disabled',
        1: 'running',
        2: 'paused',
        3: 'completed',
        4: 'cancelled',
        5: 'stopped',
        6: 'recovering',
        7: 'failed',
        8: 'na',
        9: 'scheduled'
    }

    interval_map: ClassVar[dict[str, str]] = {
        'ms': 'milliseconds',
        's':  'seconds',
        'm':  'minutes',
        'h':  'hours',
        'd':  'days'
    }
########## CLASS INIT AND DESTRUCTOR ##########
    def __init__(self,
                 logger: Logger,  # type: ignore
                 version,
                 tc,  # type: ignore
                 task_register: dict,
                 cb_shutdown: callable): # type: ignore
        try:
            logger.debug ({'msg': f'$p${__VERSION__}$p$ $a$constructor launched...$a$', 'dvc': 'PTCC', 'ip': '0.0.0.0', 'cls': __class__, 'acc': tc.waiting})
            gc.collect()
            self._mem                  = gc.mem_free()  # type: ignore
            self._log                  = logger
            self._tc                   = tc
            self._max_task_name_length = 0
            self.task_register: dict   = task_register
            self.cb_shutdown: callable = cb_shutdown    # type: ignore
            self._shutdown: bool       = False
            self.__is_alive: bool      = False
            self.txt_task: str         = 'Task'
            self.txt_tasks: str        = 'asynchronous tasks'
            self.txt_async_func: str   = 'Asynchronous function'
            self.txt_cancelling: str   = 'Cancelling'
            self.txt_not_found: str    = 'not found'
            # Calculate the interval multiplier mx based on the configured time unit
            for task_name in self.task_register:
                self.set_interval_multiplier(task_name)
                # Ensure the task name is not too long
                if len (task_name) > self._max_task_name_length:
                    self._max_task_name_length = len (task_name) - 1
        finally:
            self._log.debug ({'msg': f'$p${__VERSION__}$p$ $a$constructor finished$a$ - mem free $p${gc.mem_free()} bytes$p$', 'cls': __class__, 'src': __name__, 'acc': self._tc.success})
            gc.collect()
    def destructor (self):
        try:
            self._log.debug ({'msg': f'Version: $p${__VERSION__}$p$ $a$destructor launched...$a$', 'cls': __class__, 'acc': self._tc.waiting})
            self.txt_task = None
            self.txt_tasks = None
            self.txt_async_func = None
            self.txt_cancelling = None
            self.txt_not_found = None
            self._log.debug ({'msg': f'Version: $p${__VERSION__}$p$ $a$destructor finished.$a$', 'cls': __class__, 'acc': self._tc.success})
        finally:
            gc.collect()
########## CLASS PROPERTIES ##########
    def __version (self):
        return __VERSION__
    def __repr__ (self):
        return f'{self.__class__} Ver.: ({__VERSION__})'
    def __str__ (self):
        return f'{self.__class__}'

########## TASK CREATION / RUNNING METHODS ##########
    def add_task (self, name: str):
        try:
            for task_name in self.task_register:
                if task_name == name:
                    task = self.task_register[task_name]['task']
                    if task and (not task.done() or self.task_register[task_name]['state'] == self.State.RUNNING):
                        self._log.warning ({'msg': f'{self.txt_task} $p$<{task_name}>$p$ is already {self.S2T[self.State.RUNNING]}', 'acc': self._tc.waiting})
                        return
                    # Make sure the task actually only runs once, even if it encounters an error
                    elif self.task_register[task_name]['ro']:
                        try:
                            self.task_register[task_name]['rc'] = 0
                        except KeyError:
                            self.task_register[task_name].setdefault('mr', 0)
                    self.create_task (task_name)
        except KeyError:
            self._log.warning ({'msg': f'{self.txt_task} $p$<{name}>$p$ {self.txt_not_found}', 'acc': self._tc.error})

    def create_task(self, task_name: str):
        # Create a task
        original_coro = self.task_register[task_name]['fnc']
        interval      = self.task_register[task_name]['intv']

        async def wrapped_coro(task_name=task_name, task_info=self.task_register[task_name]):
            task_info.setdefault('_exc', None)
            task_info.setdefault('rc', 0)
            task_info.setdefault('mr', 5)
            task_info.setdefault('crash_log', [])
            task_info.setdefault('rc', 0)
            while True:
                try:
                    if task_info['state'] == self.State.RECOVERING:
                        self._log.info({
                            'msg': f'Task $f${task_name}$f$ recovered from crash $p$#{task_info["rc"]}$p$ and is {self.S2T[self.State.RUNNING]} again.',
                            'acc': self._tc.success
                        })
                    task_info['state'] = self.State.RUNNING

                    await original_coro (name=task_name, task_info=task_info)

                    task_info['state'] = self.State.COMPLETED if task_info['state'] != self.State.STOPPED else self.State.STOPPED
                    break  # Task finished normally
                except asyncio.CancelledError:
                    task_info['state'] = self.State.CANCELLED
                    raise
                except Exception as ex:
                    task_info['_exc'] = ex
                    task_info['rc'] += 1

                    # Record crash log
                    if len(task_info['crash_log']) >= 5:  # Keep only last 5
                        task_info['crash_log'].pop(0)
                    task_info['crash_log'].append((type(ex).__name__, str(ex)))

                    task_info['state'] = self.State.RECOVERING

                    self._log.warning({
                        'msg': f'Task $f${task_name}$f$ $i${task_info["id"]}$i$ crashed with $x${repr(ex)}$x$ Retry $p${task_info["rc"]}/{task_info["mr"]}$p$',
                        'acc': self._tc.bred
                    })

                    if task_info['rc'] >= task_info['mr']:
                        task_info['state'] = self.State.FAILED
                        self._log.critical({
                            'msg': f'Task $f${task_name}$f$ $i${task_info["id"]}$i$ permanently failed after $p${task_info["rc"]}$p$ retries.'
                        })
                        break
                await asyncio.sleep(5)

        task = asyncio.create_task(wrapped_coro())
        self.task_register[task_name]['id']   = id(task)
        self.task_register[task_name]['task'] = task

        if not task.done():
            txt = '$p$run-once$p$' if self.task_register[task_name]['ro'] else '$p$periodic$p$'
            txt += f', Interval = $p${interval} {self.task_register[task_name].get('unit', 's')}$p$'
            self._log.debug({
                'msg': f'$f${task_name}$f$, Id: $i${self.task_register[task_name]["id"]}$i$, Type: {txt} $a$has been created$a$',
                'acc': self._tc.success
            })

    def __create_all_tasks (self):
        self._log.debug ({'msg': f'$a$Initialising {self.txt_tasks} engine...$a$', 'acc': self._tc.waiting})
        for task_name, task_info in self.task_register.items():
            try:
                # Check if the function is callable and if the task is enabled
                if not task_info['run']:
                    task_info['state'] = self.State.DISABLED
                    self._log.warning ({'msg': f'$f$<{task_name}>$f$ {self.S2T[self.State.DISABLED]}', 'acc': self._tc.ts})
                    continue
                if not callable(task_info['fnc']):
                    self._log.warning ({'msg': f'$f$<{task_name}>$f$ is not a proper {self.txt_async_func} or does not exist'})
                    continue
                else:
                    self.create_task (task_name=task_name)
            except Exception as ex:
                self._log.error ({'msg': f'Error {repr(ex)} creating $f$<{task_name}>$f$', 'fnc': '__create_all_tasks'})

########## TASK CONTROL METHODS ##########
    # Wrapper function for __cancel_task
    def cancel_task (self, task_name: str=None, stop: bool=False): # type: ignore
        asyncio.run (self.__cancel_task (task_name=task_name, stop=stop))
    async def __cancel_task (self, task_name: str=None, stop: bool=False): # type: ignore
        if task_name is None:
            raise ValueError ('Task name must be provided')
        try:
            task = self.task_register[task_name]['task']
            if task and self.task_register[task_name]['id'] != 0:
                try:
                    task.cancel() # Cancel the task
                    await task
                except asyncio.CancelledError:
                    # Make sure the task has cancelled
                    while not task.done():
                        await asyncio.sleep (0.1)
                    state = self.State.STOPPED if stop else self.State.COMPLETED
                    self.task_register[task_name]['state'] = state
                    # Indicate in the task register that the task has been cancelled
                    self.task_register[task_name]['id']    = 0
                    self.task_register[task_name]['task']  = None
                    color = self.get_state_color (state)
                    # Once the while loop is done, the task is cancelled
                    self._log.info ({'msg': f'$f${task_name}$f$ $i${id(task)}$i$ {color}has {self.S2T[state]}', 'acc': self._tc.success})
                    gc.collect()
        except (ValueError, KeyError):
            self.__log_task_not_found (task_name=task_name, fnc='cancel_task')
        except Exception as ex:
            self._log.trace ({'exc': ex, 'cls': __class__, 'fnc': 'cancel_task'})
    # Cancel all tasks
    # This function is called when the program is shutting down
    def cancel_all_tasks (self):
        for task_name in self.task_register:
            if self.task_register[task_name]['id'] != 0 and self.task_register[task_name]['state'] == self.State.RUNNING:
                self.cancel_task (task_name=task_name)
    # Pause a task by ID or task_name
    def pause_task (self, task_name: str):
        if task_name in self.task_register and self.task_register[task_name]['state'] == self.State.RUNNING:
            if self.task_register[task_name]['cp']:
                self.task_register[task_name]['state'] = self.State.PAUSED
                self._log.info ({'msg': f'Pausing task $f${task_name}$f$'})
            else:
                self._log.warning ({'msg': f'Task $f${task_name}$f$ cannot be paused', 'acc': self._tc.warning})
    # Resume a task by ID or task_name
    def resume_task (self, task_name: str):
        if task_name in self.task_register and self.task_register[task_name]['state'] == self.State.PAUSED:
            if self.task_register[task_name]['cp']:
                self.task_register[task_name]['state'] = self.State.RUNNING
                self._log.info ({'msg': f'Resuming task $f${task_name}$f$'})
            else:
                self._log.warning ({'msg': f'Task $f${task_name}$f$ cannot be resumed', 'acc': self._tc.warning})
    def stop_task (self, task_name: str):
        if task_name in self.task_register and self.task_register[task_name]['state'] in (self.State.RUNNING, self.State.PAUSED):
            if self.task_register[task_name]['cp']:
                self._log.info ({'msg': f'Stopping task $f${task_name}$f$'})
                self.cancel_task(task_name=task_name, stop=True)
            else:
                self._log.warning ({'msg': f'Task $f${task_name}$f$ cannot be stopped', 'acc': self._tc.warning})
        elif task_name not in self.task_register:
            self.__log_task_not_found (task_name=task_name, fnc='stop_task')
        else:
            self._log.warning ({'msg': f'Task $f${task_name}$f$ is not running', 'acc': self._tc.warning})
    # Async Restart task a task by ID or task_name
    async def restart_task_async(self, task_name: str | None = None):
        interval = 1
        delay    = 5
        await self.__cancel_task(task_name=task_name)
        while delay > 0 and self.task_register[task_name]['id'] != 0:
            delay -= interval
            await asyncio.sleep(1)  # Non-blocking sleep
        self.add_task(name=task_name)
    # Async wrapper to Restart a task by ID or task_name
    def restart_task (self, task_name: str | None=None): # type: ignore
        try:
            _ = asyncio.get_event_loop()
            asyncio.create_task(self.restart_task_async(task_name=task_name))
        except RuntimeError:
            asyncio.run (self.restart_task_async(task_name=task_name))
########## TASK MISCELLANEOUS METHODS ##########
    # Check if all tasks are done
    # This function is called when the program is shutting down
    def check_tasks_done (self):
        for task_name in self.task_register:
            if self.task_register[task_name]['id'] != 0:
                if not self.task_register[task_name]['task'].done():
                    self._log.warning ({'msg': f'Task $f${task_name}$f$ $a$still {self.S2T[self.State.RUNNING]}$a$', 'acc': self._tc.waiting})
                else:
                    self._log.info ({'msg': f'Task $f${task_name}$f$ $a${self.S2T[self.State.COMPLETED]}$a$', 'acc': self._tc.success})
    def task_status(self, task_name: str, task_info: dict, failed_only: bool = True):
        # Get the current task state - if not set, set to default
        try:
            state = task_info.get('state', self.State.DISABLED)
            txt_state = self.S2T[state]
            # Define corresponding state color
            color = self.get_state_color (state)
            # Format status message
            msg = f'$f${task_name}$f$ $i${task_info["id"]}$i$ {color}{txt_state.upper()}{self._tc.end}'
            # Log the state according to severity
            if state in (self.State.RUNNING, self.State.COMPLETED, self.State.DISABLED, self.State.PAUSED) and not failed_only:
                self._log.info ({'msg': msg})
            elif state == self.State.RECOVERING:
                self._log.warning ({'msg': msg})
            elif not failed_only:
                self._log.info ({'msg': msg})
        except Exception as ex:
            sys.print_exception (ex)
            self._log.error ({'msg': f'{ex!r}', 'fnc': 'task_status'})

        # Retrieve crash log if task has failed
        if state == self.State.FAILED:
            crash_log = task_info.get('crash_log', [])
            if crash_log:
                for idx, (exctype, excmsg) in enumerate(crash_log):
                    self._log.error ({
                        'msg': f'$f${task_name}$f$ - Crash $p${idx+1}$p$: $x$[{exctype}]: {excmsg}$x$'
                    })

        # Restart logic only if task object is finished
        if state in (self.State.FAILED, self.State.RECOVERING):
            task = task_info.get('task', None)
            if task and task.done():
                self._log.warning({'msg': f'Restarting $f${task_name}$f$ due to {color}{txt_state.upper()}{self._tc.end}'})
                self.task_register[task_name]['rc'] = 0
                self.restart_task(task_name)

    def task_status_all (self, failed_only: bool = True):
        tot     = len(self.task_register)
        dis     = 0
        scd     = 0
        act     = 0
        psd     = 0
        fail    = 0
        stopped = 0
        for task_name, task_info in self.task_register.items():
            if not task_info['run'] and task_info.get('state') != self.State.RUNNING:
                dis += 1
            else:
                scd += 1
            self.task_status (task_name, task_info, failed_only=failed_only)
            if task_info.get('state') == self.State.RUNNING:
                act += 1
            if task_info.get('state') == self.State.PAUSED:
                psd += 1
            if task_info.get('state') == self.State.FAILED:
                fail += 1
            if task_info.get('state') == self.State.STOPPED:
                stopped += 1
            color  = self._tc.critical if act < scd else self._tc.success
            colorf = self._tc.critical if fail > 0 else self._tc.success
        msg = f'{self._tc.info}Total {self.txt_tasks}: $a${tot}$a${self._tc.info}, Scheduled $a${scd}$a$ {self._tc.info}, Running: {color}{act}{self._tc.info}, Stopped: {self._tc.critical}{stopped}{self._tc.info}, Paused: {self._tc.waiting}{psd} {self._tc.info}, Disabled: {self._tc.ts}{dis}{self._tc.info}, Failed: {colorf}{fail}{self._tc.end}'
        self._log.debug({'msg': msg, 'acc': self._tc.success})
        gc.collect()

    def get_task_state (self) -> dict:
        tasks = {}
        for task_name, task_info in self.task_register.items():
            tasks[task_name] = {'Status': task_info.get('state', 'unknown'), 'Failures': task_info.get('rc', 0)}
        return tasks

    def __log_task_not_found (self, task_name: str | None=None, fnc: str | None=None): # type: ignore
        if task_name is not None:
            self._log.warning ({'msg': f'$i${task_name}$i$ {self.txt_not_found}', 'fnc': fnc})

    @property
    def is_alive (self):
        return self.__is_alive
    def print_task_status (self):
        max_key_len = 0
        max_val_len = 0
        # Find the length of the longest value in the dictionary
        max_key_len = max((len(key) for key in self.task_register), default=0)
        max_val_len = max(
            (len(str(value))
            for task_info in self.task_register.values()
            for key, value in task_info.items()
            if key in ('state', 'id', 'type')),
            default=0
        )
        s = f'{self._tc.info}{'Task Name':<{max_key_len}}\t'
        s += f'{'ID':<{max_val_len}}\t'
        s += f'{'Type':<{max_val_len}}\t'
        s += f'{'Interval':<{max_val_len}}\t'
        s += f'{'State':<{max_val_len}}\t'
        s += f'{'Errors':<{max_val_len}}{self._tc.end}'
        self._log.aprint ('\n')
        self._log.aprint (s)
        self._log.aprint (f'{self._tc.info}' + '-' * (len (s) + 15), end = self._tc.end + '\n')

        for task_name, task_info in self.task_register.items():
            state     = task_info.get('state', 8)
            txt_state = self.S2T[state]
            # Define corresponding state color
            color = self.get_state_color (state)
            if task_info.get('ro'):
                task_type = 'run once'
            else:
                task_type = 'periodic'
            if len (task_name) < 8:
                task_name += ' ' * (8 - len (task_name))
            s =  f'{self._tc.success}{task_name:<{max_key_len}}\t'
            s += f'{self._tc.id}{task_info['id']!s:<{max_val_len}}\t'
            s += f'{self._tc.par}{task_type:<{max_val_len}}\t'
            i =  f'{task_info.get('intv', 0)} {task_info.get('unit', 's')}'
            s += f'{self._tc.info}{i:<{max_val_len}}\t'
            s += f'{color}{txt_state.upper()}{self._tc.end}'
            tab = '\t\t' if len (txt_state) < 8 else '\t'
            color = self._tc.critical if int (task_info['rc']) > 0 else self._tc.success
            s += f'{color}{tab}{task_info["rc"]!s:<{max_val_len}}{self._tc.end}'
            self._log.aprint (s)
        del s
        gc.collect()
    def print_task_register (self):
        for task_name, task_info in self.task_register.items():
            self._log.aprint (f'{self._tc.fnc}{task_name}: {self._tc.par}{task_info}{self._tc.end}')
    def get_failed_tasks(self):
        failed_tasks = []
        for task_name, task_info in self.task_register.items():
            if task_info.get('state') in (self.State.FAILED, self.State.RECOVERING):
                failed_tasks.append(task_name)
        return failed_tasks
    def get_failed_task_count(self):
        return len(self.get_failed_tasks())
    def task_interval(self, task_name: str, params: list | None = None):
        # Check that task exists
        if task_name in self.task_register:
            # Check if params are to be set or just to get current interval
            if params is None or len (params) < 2:
                # Only get current interval
                iv, u, mx = self.get_task_interval (task_name=task_name)
                self._log.info ({'msg': f'Current interval for $f${task_name}$f$ is $p${iv} {u}$p$; Multiplier: $p${mx}$p$'})
                return
            elif not is_int (params[0]) and not is_float (params[0]):
                raise ValueError (f'Invalid type /{type(params[1])}/; must be int or float')
            elif params[1] not in self.interval_map:
                raise ValueError (f'Invalid unit /{params[1]}/; must be one of {list(self.interval_map.keys())}')
            elif len (params) > 2:
                raise ValueError (f'Too many parameters; expected 2, got /{len(params)}/')
            else:
                self.task_register[task_name]['intv'] = int (params[0]) if is_int (params[0]) else float (params[0])
                self.task_register[task_name]['unit'] = params[1]
                self.set_interval_multiplier(task_name)
            self._log.info ({'msg': f'New interval for $f${task_name}$f$ is $p${self.task_register[task_name]['intv']} {self.interval_map[self.task_register[task_name]['unit']]}$p$; Multiplier: $p${self.task_register[task_name]['mx']}$p$'})
        else:
            raise NotImplementedError (f'$f${task_name}$f$ {self.txt_not_found}')
    def get_task_interval(self, task_name: str):
        if task_name in self.task_register:
            interval = self.task_register[task_name].get('intv', 0)
            unit     = self.task_register[task_name].get('unit', 'na')
            mx       = self.task_register[task_name].get('mx', 0)
            return interval, self.interval_map[unit], mx
        else:
            return None, None
    def set_interval_multiplier(self, task_name: str):
        if self.task_register[task_name]['unit'] == 'ms':
            self.task_register[task_name]['mx'] = 0.001
        elif self.task_register[task_name]['unit'] == 's':
            self.task_register[task_name]['mx'] = 1
        elif self.task_register[task_name]['unit'] == 'm':
            self.task_register[task_name]['mx'] = 60
        elif self.task_register[task_name]['unit'] == 'h':
            self.task_register[task_name]['mx'] = 3600
        elif self.task_register[task_name]['unit'] == 'd':
            self.task_register[task_name]['mx'] = 86400
        else:
            raise ValueError (f'Invalid time unit {self.task_register[task_name]["unit"]} for task {task_name}')
    def get_state_color(self, state: int) -> str:
        """Get the color code for a given task state."""
        return (
            self._tc.success  if state == self.State.RUNNING    else
            self._tc.warning  if state == self.State.RECOVERING else
            self._tc.info     if state == self.State.COMPLETED  else
            self._tc.critical if state == self.State.FAILED     else
            self._tc.ts       if state == self.State.DISABLED   else
            self._tc.waiting  if state == self.State.PAUSED     else
            self._tc.critical if state == self.State.STOPPED    else
            self._tc.waiting
        )
########## MAIN START/STOP FUNCTIONS ##########
    def stop (self):
        # Avoid cascading shutdown
        if not self._shutdown:
            self._shutdown = True
    def shutdown (self):
        if self._shutdown:
            self.__is_alive = False
            self.cancel_all_tasks()
            self._log.info ({'msg': '$a$has terminated$a$', 'cls': __class__, 'acc': self._tc.success})
    async def tm_main (self):
        _fnc_name = 'tm_main'
        try:
            gc.collect()
            self.__create_all_tasks()
            self.__is_alive = True
            gc.collect()
            self._log.debug ({'msg': f'$a$Memory used by$a$ $c${__class__}$c$ $p${self._mem - gc.mem_free()} bytes$p$', 'acc': self._tc.success}) # type: ignore
            while not self._shutdown:
                await asyncio.sleep (3)
            self._log.info ({'msg': '$a$Shutdown request received$a$', 'cls': __class__, 'fnc': _fnc_name, 'acc': self._tc.waiting})
        except KeyboardInterrupt as ex:
            self._log.trace ({'exc': ex, 'cls': __class__, 'fnc': _fnc_name})
            raise
        except Exception as ex:
            self._log.trace ({'exc': ex, 'cls': __class__, 'fnc': _fnc_name})
            raise
        finally:
            # Notify the parent object of the shutdown using the callback function
            # The parent process will initiate a controlled shutdown along the tree of all created objects
            self.cb_shutdown ()

##### HELPER FUNCTIONS #####
def is_int(val):
    return str(val).isdigit()

def is_float(val):
    try:
        float(val)
        return True
    except ValueError:
        return False

