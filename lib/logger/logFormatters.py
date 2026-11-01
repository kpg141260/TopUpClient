__VERSION__ = "0.6.0.24"
# ruff: noqa: RUF100, UP025, UP004, I001, F401, BLE001
# -*- coding: utf-8 -*-
import time
import gc
import re
import ujson           as json
from   ansi_esc        import text_colors as tc
from   logger.logger   import dbg_lvls

# Ensure `StringIO` is available across MicroPython ports (io / uio)
try:
    import io
except Exception:
    io = None

if io is None or not hasattr(io, 'StringIO'):
    try:
        import uio as io
    except Exception:
        io = None

if io is None or not hasattr(io, 'StringIO'):
    class _StringIO:
        def __init__(self):
            self._buf = []
        def write(self, s):
            try:
                self._buf.append(str(s))
            except Exception:  # noqa: S110
                pass
        def getvalue(self):
            return ''.join(self._buf)
        def close(self):
            self._buf = None

    class _IOMod:
        pass

    _IOMod.StringIO = _StringIO
    io = _IOMod

class _ExceptionStringWriter:
    def __init__(self):
        self._buf = []
    def write(self, s):
        try:
            self._buf.append(str(s))
        except Exception:  # noqa: S110
            pass
    def getvalue(self):
        return ''.join(self._buf)
    def close(self):
        self._buf = None

def __func_match (match):
    return f'{tc.fnc}{match.group(0)}{tc.end}'
def _line_match (match):
    return f'{tc.lno}{match.group(0)}{tc.end}'
try:
    from sys import print_exception
except ImportError:  # pragma: no cover
    import traceback

    def print_exception(ex):
        traceback.print_exc()

###############################################################################
# CLASS LOG-FORMATTERS
###############################################################################
class LogFormatter:
    def __init__(self,
                 log_fmt: dict,
                 use_color: bool | None=None,
                 use_brkts: bool | None=None,
                 use_eid: bool | None=None,
                 use_ampm: bool | None=None,
                 use_ts: bool | None=None,
                 use_pad: bool | None=None,
                 align: str='center',
                 name=''):
        self._txt_dm        = ' \x1b[0m sub-dictionary missing'
        self._name          = name
        self._log_col       = {}
        self._log_lbls      = {}
        self._log_conf      = log_fmt['settings'].copy()
        self._log_fmt       = log_fmt['logFormat'].copy()
        # EVENT TAG MAP STRUCTURE: [key]=long-tag [0]=short-tag, [1]=prefix, [2]=suffix, [3]=color
        # Deep-copy the config pieces we will mutate per-instance
        # ujson double-serialize is a cheap deepcopy in MicroPython
        try:
            self._orig_cfg = json.loads(json.dumps(log_fmt))
        except Exception:
            # fallback to shallow copies if ujson can't serialize something
            self._orig_cfg = {
                'evt_tag_map': {k: v[:] for k, v in log_fmt.get('evt_tag_map', {}).items()},
                'filters':     {k: v    for k, v in log_fmt.get('filters',     {}).items()},
                'logColors':   {k: v    for k, v in log_fmt.get('logColors',   {}).items()},
                'logFormat':   {k: v    for k, v in log_fmt.get('logFormat',   {}).items()},
                'settings':    {k: v    for k, v in log_fmt.get('settings',    {}).items()},
                'dbg_lvl_map': {k: v[:] for k, v in log_fmt.get('dbg_lvl_map', {}).items()}
            }
        # build instance-local tag map (copy lists so instances don't share mutable lists)
        self._evt_tag_map = self._build_evt_tag_lookup(self._orig_cfg.get('evt_tag_map', {}))
        self._filters     = self._orig_cfg.get('filters', {})
        self.rxf          = regex_filters
        self.rxf.init_cache (self._filters)

        self._evt_fmt_lbls = log_fmt['logFormat']['evt_labels'].copy()

        # Note: flags defined in log_fmt are overwritten and must be passed explicitly in the constructor
        self._use_col   = use_color if use_color is not None else self._orig_cfg['logFormat'].get('use_color', False)
        self._use_eid   = use_eid   if use_eid   is not None else self._orig_cfg['logFormat'].get('use_eid',   False)
        self._use_ampm  = use_ampm  if use_ampm  is not None else self._orig_cfg['logFormat'].get('use_ampm',  False)
        self._use_ts    = use_ts    if use_ts    is not None else self._orig_cfg['logFormat'].get('use_ts',    False)
        self._use_brkts = use_brkts if use_brkts is not None else self._orig_cfg['logFormat'].get('use_brkts', True)
        self._use_pad   = use_pad   if use_pad   is not None else self._orig_cfg['logFormat'].get('use_pad',   False)
        self._align     = align     if align     is not None else self._orig_cfg['logFormat'].get('pad_align', 'center')
        self._show_mem  = self._orig_cfg['logFormat'].get('show_mem', False)
        # Sanity check alignment value
        self._align = self._align if self._align in ('left', 'l', 'right', 'r', 'center', 'c') else 'center'

        # Set up color scheme if requested
        if use_color:
            self._log_col  = log_fmt['logColors'].copy()
            # Set default colors if not provided
            self._base_col = self._log_col.get  ('off', "\u001b[38;5;8m")
            acc = self._evt_tag_map.get ('acc', None)
            if acc is not None and isinstance (acc, list) and len (acc) >= 3:
                self._accent = acc[2]
            else:
                self._accent = "\u001b[38;5;46m"
        else:
            self._log_col  = {}
            self._base_col = ''
            self._accent   = ''

        # Prepare label padding if requested
        _max_lbl_len = 0
        if self._use_pad:
            for k, v in self._orig_cfg['dbg_lvl_map'].items():
                _max_lbl_len = max (_max_lbl_len, len (v[1]))
            for k, v in self._orig_cfg['dbg_lvl_map'].items():
                self._log_lbls.setdefault (k, self.pad_string (v[1], _max_lbl_len, self._align))
        else:
            self._log_lbls = {}

    def __destruct__ (self):
        self._log_col.clear()
        del self._log_col
        self._log_fmt.clear()
        del self._log_fmt
        self._evt_tag_map.clear()
        del self._evt_tag_map
        self._evt_fmt_lbls.clear()
        del self._evt_fmt_lbls
        self._log_conf.clear()
        self._orig_cfg.clear()
        del self._orig_cfg
        self._log_lbls.clear()
        del self._log_lbls
        del self._filters
        del self._log_conf
        del self._base_col
        del self._accent
        del self.rxf
        del self._name
        del self._txt_dm
        gc.collect()
    def __repr__ (self):
        return f'{self.__class__.__name__} Ver.: ({__VERSION__})'
    def __str__ (self):
        return f'{self.__class__.__name__}'
    def format_output(self, event_log):
        """ Format the event log dictionary into a string according to the specified format fields.
            Updated to minimize temporary allocations and call gc.collect() to free fragmentation. """
        if not isinstance(event_log, (dict, str)):
            raise TypeError(f'{__class__.__name__} event_log must be a \'dictionary\' or \'string\'')
        if isinstance(event_log, str) or not any(key in event_log for key in self._evt_tag_map):
            return event_log

        event = self._pre_process_event(event_log)

        parts = []
        sep = self._log_fmt.get('separator', ' ')

        for k in self._evt_fmt_lbls:
            val = event.get(k, '')
            if val in ('', None):
                continue

            # Special handling for 'msg' field with colorization
            if k == 'msg' and self._use_col:
                val = event.get('msg', '')
                if val in ('', None):
                    continue
                val = self._colorize(val)

            # safe extraction of tag map items
            tag_info = self._evt_tag_map.get(k, ['', '', '', ''])
            prefix = tag_info[1] if len(tag_info) > 1 else ''
            suffix = tag_info[2] if len(tag_info) > 2 else ''
            color  = tag_info[3] if len(tag_info) > 3 else ''

            if self._use_brkts and not self._use_col:
                part = f"{prefix}{val}{suffix}"
            elif self._use_brkts and self._use_col:
                end = self._log_col.get('end', '')
                part = f"{color}{prefix}{val}{suffix}{end}"
            elif not self._use_brkts and self._use_col:
                end = self._log_col.get('end', '')
                part = f"{color}{val}{end}"
            else:
                part = str(val)

            parts.append(part)

        # Post-process parts in-place to avoid extra lists/dicts
        for idx, part in enumerate(parts):
            p = part
            if ('\x1b' in p or '\u001b' in p) and not self._use_col:
                p = self.strip_esc_seq(p)
            p = self.strip_tags(p)
            if not self._use_brkts:
                p = self.strip_brackets(p, self._filters.get('brackets', '[]<>{}()'))
            p = self.strip_spaces(p)

            parts[idx] = p

        result = sep.join(parts)

        if self._use_pad:
            for k, v in self._orig_cfg['dbg_lvl_map'].items():
                if v[1] in result:
                    result = result.replace(v[1], self._log_lbls[k])
                    break
        # attempt to reduce fragmentation immediately
        gc.collect()
        return result
    def format_remove (self, s):
        """ Remove any $x$...$x$ formatting from the given string. """
        if not isinstance (s, str):
            raise TypeError (f'{__class__.__name__} remove_formatting input must be a \'string\'')
        # Remove any $x$...$x$ tags
        s = self.strip_tags (s)
        # Remove any ANSI escape sequences
        s = self.strip_esc_seq (s)
        # Remove any brackets if configured
        if not self._use_brkts:
            s = self.strip_brackets (s, self._filters['brackets'])
        return self.strip_spaces (s)
    def _format_trace(self, exception: Exception):
        """Format exception to single-line string and apply color substitutions."""
        if exception is None:
            return ''

        # color vars (empty when not using colors)
        if self._use_col:
            col_crit = self._log_col.get('critical', '')
            col_trc  = self._log_col.get('trace',    '')
            col_err  = self._log_col.get('error',    '')
            col_fnc  = self._log_col.get('function', '')
            col_fn   = self._log_col.get('success',  '')
            col_end  = self._log_col.get('end',      '')
        else:
            col_crit = col_trc = col_err = col_end = col_fn = col_fnc = ''

        # capture exception output
        try:
            output = io.StringIO()
        except Exception:
            output = _ExceptionStringWriter()

        try:
            print_exception(exception, output)
        except Exception:
            # fallback if print_exception signature differs
            try:
                output.write(str(exception))
            except Exception:  # noqa: S110
                pass
        msg = output.getvalue()
        try:
            output.close()
        except Exception:  # noqa: S110
            pass

        # collapse to single line and simplify text
        msg = ' '.join(msg.splitlines())
        #print (f'{tc.debug}Raw exception string: {tc.end}{msg}')
        msg = msg.replace('Traceback (most recent call last):', f'{col_crit}Exception:{col_end}')
        msg = msg.replace('File ', '')
        #print (f'{tc.debug}Simplified exception string: {tc.par}{msg}{col_end}')
        msg = msg.replace('in <module>', '')
        # Find and replace the actual function causing the issue
        m = self.rxf.compiled_pattern('func').search(msg)
        #print (f'{tc.debug}Function match search result: {tc.par}{m}{col_end}' if m else f'{tc.debug}Function match search result: {tc.par}No match found{col_end}')
        f = m.group(0).replace(', in ', '') if m else ''
        #print (f'{tc.debug}Function match extracted function: {tc.par}{f}{col_end}' if f else f'{tc.debug}Function match extracted function: {tc.par}No function extracted{col_end}')
        r = f'{col_trc}, in module: {col_fnc}{f}{col_end}' if f != '' else ''
        #print (f'{tc.debug}Function match search result: {tc.par}{m.group(0)} - {f} - {r}{col_end}')
        msg = msg.replace(m.group(0), r) if m else msg

        #fnc = {col_fn + fnc + col_end} if fnc else ''
        #print (f'{tc.debug}Function match search result: {tc.par}{fnc}{col_end}')
        #msg = msg.replace(', in ', ', in method: ')

        # substitutions (use compiled patterns where available)
        subs = [
            ('quote', lambda m: f'{col_trc}{m.group(1)}{col_end}'),  # "text"
            ('brac',  lambda m: f'{col_trc}{m.group(1)}{col_end}'),  # <text>
            ('err',   lambda m: f'{col_crit}{m.group(1)}{col_err}'), # SomethingError:
            ('fn',    lambda m: f'{col_fn}{m.group(1)}{col_end}'),   # filename match
            ('func',  lambda m: f'{col_fn}{m.group(1)}{col_end}'),   # filename match
            ('line',  _line_match)                                  # line N
        ]
        for name, repl in subs:
            try:
                pat = self.rxf.compiled_pattern(name)
                msg = pat.sub(repl, msg)
            except Exception:  # noqa: S110
                # ignore missing/invalid patterns
                pass

        # remove leftover markers and ensure trailing reset
        msg = msg.replace('<in ', '').replace('>', '')
        msg = self.strip_spaces(msg)
        if col_end and not msg.endswith(col_end):
            msg = msg + col_end
        # clean up
        del subs
        gc.collect()
        return msg

    def _pre_process_event ( self, event_log: dict):
        event_log = event_log.copy()
        # Reset base color and label color
        # EVENT TAG STRUCTURE: [0]=short-tag, [1]=prefix, [2]=suffix, [3]=color
        self._evt_tag_map['lbl'][3] = ''
        self._evt_tag_map['msg'][3] = ''

        # Process event_log dictionary keys according to specified format
        if self._use_col:
            # Set the base color of the event
            self._base_col = self._get_level_color (event_log['lvl'])
            # Check if the `acc` key is present in the event log and set color accordingly
            self._accent = event_log.get('acc', '') #if event_log.get('acc', '') != '' else self._accent
        else:
            # No colorization
            self._base_col = ''
            self._accent   = ''
            # Strip any tags from the event message
            event_log['msg'] = self.strip_tags (event_log.get('msg', ''))

        # Set label and message colors
        self._evt_tag_map['lbl'][3] = self._base_col
        self._evt_tag_map['msg'][3] = self._base_col

        # If an exception object is provided, format it and set as the message
        if 'exc' in event_log and event_log['exc'] is not None:
            event_log['msg'] = self._format_trace(event_log['exc'])
            event_log.pop('exc', None)

        # Format log identifier with leading zeros and prefix, if defined
        eid_formatted = ''
        if self._use_eid:
            try:
                eid_formatted = f'{self._log_fmt['eid_prefix']}{event_log.get('eid', None):{self._log_fmt.get('eid_format', '06d')}}{self._log_fmt['eid_suffix']}'
            except (ValueError, TypeError):
                eid_formatted = ''
        event_log['eid'] = eid_formatted

        # Format timestamp if required
        ts = ''
        if self._use_ts:
            ts = event_log.get('ts', '')
            if not self.is_timestamp(ts):
                ts = self.get_time_stamp(
                    format=self._log_fmt.get('ts_format', '%Y-%m-%d %H:%M:%S'),
                    use_12_hour=self._use_ampm
                ) or ''
        event_log['ts'] = ts

        if self._show_mem:
            mem_info = f' [{gc.mem_free()} bytes free]'
            if self._use_col:
                mem_info = f' {self._evt_tag_map['mem'][3]}{mem_info}{self._log_col.get("end", "")}'
            event_log['mem'] = mem_info

        for key in list(event_log.keys()):
            # Remove any keys not in the event format fields, except for 'lvl'
            if key not in self._evt_fmt_lbls and key != 'lvl':
                del event_log[key]
            else:
                if  event_log[key] is not None and isinstance (event_log[key], str):
                    # Remove any leading/trailing brackets
                    event_log[key] = self.strip_brackets (event_log[key], self._filters['brackets'])

        return event_log
    def _colorize(self, text):
        """
        Colorize text enclosed in $tag$...$tag$ without using regex.
        Supports tag keys of 1..3 alphabetic chars (e.g. $x$, $xx$, $xxx$).
        """
        if not isinstance(text, str):
            return text
        if not self.has_tags(text):
            return self._base_col + text

        tag_map = getattr(self, '_evt_tag_map', {})
        # For each tag key, scan and replace all $tag$...$tag$ occurrences
        for tag, tag_info in tag_map.items():
            # accept 1..3 letter tags
            if not (isinstance(tag, str) and 1 <= len(tag) <= 3 and tag.isalpha()):
                raise ValueError (f'{__class__} _colorize invalid tag key: {tc.critical}{tag}{tc.end} {tag_info} - tags may only contain 1 to 3 alphabetic characters')

            open_pat = f'${tag}$'
            start = 0
            while True:
                i = text.find(open_pat, start)
                if i == -1:
                    break
                j = text.find(open_pat, i + len(open_pat))
                if j == -1:
                    break
                inner = text[i + len(open_pat): j]

                # Safely extract parts from tag_info
                # Structure: [0]=short-tag, [1]=prefix, [2]=suffix, [3]=color
                short_tag = tag_info[0] if len(tag_info) > 0 else '' # noqa
                prefix    = tag_info[1] if len(tag_info) > 1 else ''
                suffix    = tag_info[2] if len(tag_info) > 2 else ''
                color     = tag_info[3] if len(tag_info) > 3 else ''

                if self._use_brkts:
                    # include color (if any), then bracketed prefix/content/suffix, then reset to base color
                    repl = f'{color}{prefix}{inner}{suffix}{self._base_col}'
                else:
                    repl = f'{color}{prefix}{inner}{suffix}{self._base_col}'

                # Replace the whole $tag$inner$tag$ with the replacement
                text = text[:i] + repl + text[j + len(open_pat):]
                # Continue scanning after the replacement to avoid infinite loop
                start = i + len(repl)
        return text
    def _get_level_color (self, level: int) -> str:
        level_map = {
            int(dbg_lvls.OFF):      'off',
            int(dbg_lvls.DEBUG):    'debug',
            int(dbg_lvls.INFO):     'info',
            int(dbg_lvls.WARNING):  'warning',
            int(dbg_lvls.ERROR):    'error',
            int(dbg_lvls.CRITICAL): 'critical',
            int(dbg_lvls.TRACE):    'trace'
        }
        return self._log_col.get(level_map.get(level, 'off'), self._log_col.get('off', '')) if self._use_col else ''
    def _build_evt_tag_lookup (self, evt_tag_map):
        """Return dict where both full-key and first-list-element map to a copied value."""
        lookup = {}
        for full_key, lst in evt_tag_map.items():
            # always copy the list to avoid sharing and future mutation
            if isinstance(lst, list):
                copied = lst[:]  # shallow copy is enough (elements are primitives)
            else:
                copied = [lst]
            lookup[full_key] = copied
            if copied and copied[0]:
                lookup[copied[0]] = copied
        return lookup
    def set_colors (self, **kwargs):
        self._log_col = {}
        for k, v in kwargs.items():
            if isinstance (v, dict):
                for key, value in v.items():
                    if key in self._log_col:
                        self._log_col[key] = value
                    else:
                        raise AttributeError (f'{__class__} has no color attribute {key}')
            else:
                if k in self._log_col:
                    self._log_col[k] = v
                else:
                    raise AttributeError (f'{__class__} has no color attribute {key}')
    def set_event_format (self, fields: list):
        if not isinstance (fields, list):
            raise TypeError (f'{__class__} set_event_format \'fields\' must be a list of log-tag specifiers in the form of \'%abc%\'')
        self._evt_fmt_lbls = fields
    def use_colors (self, use: bool, colors: dict | None=None):
        self._use_col = use
        if self._log_colors == {}:
            self._log_colors = colors if colors is not None else {}
        if use and self._log_colors == {}:
            raise ValueError (f'{__class__} use_colors set to True but no color dictionary provided')
    def use_brkts (self, use: bool):
        self._use_brkts = use
    def use_log_id (self, use: bool):
        self._use_eid = use
    def use_12_hour (self, use: bool):
        if use == self._use_ampm:
            return
        if use:
            self._use_ampm = use
            if self._log_fmt['ts_format'] is not None and '%P' not in self._log_fmt['ts_format']:
                self._log_fmt['ts_format'] += ' %P'
        else:
            self._use_ampm = use
            if self._log_fmt['ts_format'] is not None and '%P' in self._log_fmt['ts_format']:
                self._log_fmt['ts_format'] = self._log_fmt['ts_format'].replace(' %P', '')
    ########## STATIC METHODS ##########
    @staticmethod
    def strip_esc_seq(s):
        start = s.find('\x1b[')
        while start != -1:
            end = s.find('m', start + 2)
            if end == -1:
                return s[:start]
            s = s[:start] + s[end + 1:]
            start = s.find('\x1b[', start)
        return s    
    
    @staticmethod
    def strip_tags(s, t: str = '$'):
        try:
            length = len(s)
        except (ValueError, TypeError):
            return s
        i = 0
        while i < length:
            if s[i] == '$':
                j = i + 1
                while j < length and j - i <= 3 and s[j].isalpha():
                    j += 1
                if j < length and s[j] == t:
                    s = s[:i] + s[j + 1:]
                    length = len(s)
                    continue
            i += 1
        return s
    
    @staticmethod
    def strip_brackets(s, f):
        for char in f:
            s = s.replace(char, '')
        return s    
    
    @staticmethod
    def strip_spaces (s):
        cleaned = s.strip()
        while '  ' in cleaned:
            cleaned = cleaned.replace('  ', ' ')
        return cleaned
    
    @staticmethod
    def pad_string(s, length, align: str='center'):
        """
        Pad `s` to `length` using spaces.
        align: 'left', 'right', or 'center' (default).
        """
        if align not in ('left', 'l', 'right', 'r', 'center', 'c'):
            raise ValueError (f'{__class__} pad_string invalid align value: {tc.critical}{align}{tc.end} - must be "left", "right", or "center"')
        s = str(s).strip()
        padcnt = length - len(s)
        if align in ('left', 'l'):
            return s + ' ' * padcnt
        if align in ('right', 'r'):
            return ' ' * padcnt + s
        # center (default) - keep behaviour: extra space goes to the left
        left = (padcnt // 2) + (padcnt % 2)
        right = padcnt - left
        return ' ' * left + s + ' ' * right
    
    @staticmethod
    def has_tags(s: str):
        """Return True if text contains any $x$, $xx$ or $xxx$ tag (no regex)."""
        if not isinstance(s, str):
            return False
        i = 0
        n = len(s)
        while i < n:
            if s[i] == '$':
                j = i + 1
                letters = 0
                # collect up to 3 alphabetic characters
                while j < n and s[j].isalpha() and letters < 3:
                    j += 1
                    letters += 1
                # must be at least one letter and closed by '$'
                if letters >= 1 and j < n and s[j] == '$':
                    return True
                # advance past this position to continue scanning
                i = j
            else:
                i += 1
        return False
    
    @staticmethod
    def get_time_stamp (format: str | None=None, prefix='', use_12_hour=False) -> str:
        if format is None:
            return
        tm = time.gmtime()
        hour = tm[3]
        am_pm = ''
        if use_12_hour:
            am_pm = 'AM' if hour < 12 else 'PM'
            hour = hour % 12
            if hour == 0:
                hour = 12
        format_map = {
            "%Y": f"{tm[0]:04d}", # Year
            "%m": f"{tm[1]:02d}", # Month
            "%d": f"{tm[2]:02d}", # Day
            "%H": f"{hour:02d}",  # Hour (12-hour or 24-hour)
            "%M": f"{tm[4]:02d}", # Minute
            "%S": f"{tm[5]:02d}", # Second
            "%P": am_pm           # AM/PM marker
        }
        for key, value in format_map.items():
            format = format.replace(key, value)
        return prefix + format

    @staticmethod
    def is_timestamp(s):
        if not isinstance(s, str):
            return False

        # Expected examples:
        # 2026-06-24 18:30:45
        # 2026/06/24 18:30:45
        if len(s) < 19:
            return False

        return (
            s[0:4].isdigit() and
            s[4] in ('-', '/') and
            s[5:7].isdigit() and
            s[7] in ('-', '/') and
            s[8:10].isdigit() and
            s[10] == ' ' and
            s[11:13].isdigit() and
            s[13] == ':' and
            s[14:16].isdigit() and
            s[16] == ':' and
            s[17:19].isdigit()
        )

class regex_filters:
    """
    Lightweight regex utility for MicroPython.
    Supports dynamic $x$...$x$ tag matching with caching.
    """
    _cache: dict | None = None

    @classmethod
    def init_cache(cls, patterns):
        if cls._cache is None:
            cls._cache = {}
        try:
            """Compile and cache all predefined regex patterns."""
            for name, pattern in patterns.items():
                if pattern and isinstance(pattern, str) and name not in cls._cache:
                    cls._cache[name] = re.compile(pattern)
        except Exception as e:
            cls._cache = {}
            raise RuntimeError (f"Error initializing regex cache: {e}, Pattern: {name} {pattern}")

    @classmethod
    def compiled_pattern (cls, name: str):
        """Return compiled pattern or None if not present (compat wrapper)."""
        return cls._cache.get(name)

    def _tag_color(self, tag_info, default=''):
        """Return color to use for this tag (do not mutate tag_info)."""
        if not tag_info or len(tag_info) < 4:
            return default
        return tag_info[3] or default
