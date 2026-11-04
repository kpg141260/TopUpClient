__VERSION__ = "0.5.0.2"
# ruff: noqa: RUF100, UP025, UP004, I001, F401
import re

class regex_filters:
    re_acc_pattern    = re.compile(r'\$\a\$(.*?)\$\a\$')
    re_cls_pattern    = re.compile(r'\$\c\$(.*?)\$\c\$')
    re_exc_pattern    = re.compile(r'\$\e\$(.*?)\$\e\$')
    re_fnc_pattern    = re.compile(r'\$\f\$(.*?)\$\f\$')
    re_pid_pattern    = re.compile(r'\$\i\$(.*?)\$\i\$')
    re_par_pattern    = re.compile(r'\$\p\$(.*?)\$\p\$')
    re_dvc_pattern    = re.compile(r'\$\v\$(.*?)\$\v\$')
    re_xtr_pattern    = re.compile(r'\$\x\$(.*?)\$\x\$')
    re_format_pattern = re.compile(r'\$[acdefipx]\$')
    re_remove_pattern = re.compile(r'\$\a\$|\$c\$|\$\e\$|\$\f\$|\$i\$|\$\p\$|\$v\$|\$\x\$')
    re_ip4_pattern    = re.compile(r'(\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b')
    re_web_pattern    = re.compile(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+')
    re_quote_pattern  = re.compile(r'"([^"]*)"')
    re_brac_pattern   = re.compile(r'<([^"]+)>')
    re_err_pattern    = re.compile(r'(\w+Error:)')
    re_pattern_3      = re.compile(r'(line \d+)')
    line_pattern      = r'(line \d+)'
    func_pattern      = r'in\s[\w_]+'
