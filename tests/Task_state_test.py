import io, json, sys
sys.path.append('/lib/common')
from ansi_esc import text_colors as tc

txt_cancelled: str    = 'cancelled'
txt_not_found: str    = 'not found'
txt_completed: str    = 'completed'
txt_disabled: str     = 'disabled'
txt_failed: str       = 'failed'
txt_recovering: str   = 'recovering'
txt_running: str      = 'running'


print ('Task state test started')

with open ('/config/async_tasks.json') as f:
    task_register = json.load (f)

max_val_len = 0
max_key_len = 0
# Find the length of the longest value in the dictionary
for key in task_register.keys():
    if max_key_len < len (key):
        max_key_len = len (key)
    for key, value in task_register[key].items():
        if key == 'state' or key == 'task_id':
            if len (str (value)) > max_val_len:
                max_val_len = len (str (value))
t = 'Task Name'
s = f'{tc.info}{t:<{max_key_len}}\t'
t = 'ID'
s += f'{t:<{max_val_len}}\t'
t = 'Type'
s += f'{t:<{max_val_len}}\t\t'
t = 'State'
s += f'{t}'
print (s)
print ('-' * (len (s) + 5), end = '')
print (f'{tc.end}')

for task_name, task_info in task_register.items():
    state =  task_info.get('state', 'na')
    color = tc.success  if state == txt_running else tc.warning  if state == txt_recovering else tc.info if state == txt_completed else tc.critical if state == txt_failed else tc.ts if state == txt_disabled else tc.waiting
    if task_info.get('one_shot'):
        task_type = 'one_shot'
    else:
        task_type = 'periodic'
    if len (task_name) < 8:
        task_name += ' ' * (8 - len (task_name))
    s =  f'{tc.success}{task_name:<{max_key_len}}\t{tc.fnc}'
    s += f'{tc.id}{str (task_info['id']):<{max_val_len}}\t{tc.fnc}'
    s += f'{tc.par}{task_type:<{max_val_len}}\t{tc.fnc}'
    s += f'{color}{state.upper()}{tc.end}'
    print (s)


print (f'{tc.info}Task state test completed{tc.end}')
