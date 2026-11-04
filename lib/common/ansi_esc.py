__VERSION__ = "0.6.0.13"
# ruff: noqa: RUF100, UP025, UP004, I001, F401, BLE001, S110
class text_colors:
    ESC    = '\x1b['

    # Rendition codes
    bold   = ESC + '1m'
    italic = ESC + '3m'
    ul     = ESC + '4m'

    # Base colors
    red         = ESC + '38;5;124m'
    bred        = ESC + '38;5;196m'
    green       = ESC + '38;5;40m'
    yellow      = ESC + '38;5;142m'
    cyan        = ESC + '38;5;45m'
    orange      = ESC + '38;5;166m'

    # Debug colors
    debug       = ESC + '1;38;5;250m'
    info        = ESC + '38;5;46m'
    warning     = ESC + '38;5;166m'
    error       = ESC + '1;38;5;124m'
    critical    = ESC + '1;38;5;196m'

    # Colors used for $n$ formatting codes
    acc         = ESC + '1;3;38;2;182;255;150m'
    adr         = ESC + '4;38;5;102m'
    banner      = ESC + '1;38;5;15;48;5;57m'
    ccls        = ESC + '38;5;99m'
    cmd         = ESC + '1;3;38;5;69m'
    dvc         = ESC + '1;38;5;200m'
    exc         = ESC + '1;38;5;161m'
    fnc         = ESC + '38;5;69m'
    pid         = ESC + '38;5;45m'
    label       = ESC + '38;5;14m'
    lno         = ESC + '38;5;34m'
    par         = ESC + '1;38;5;33m'
    success     = ESC + '1;3;38;2;182;255;150m'
    ts          = ESC + '38;5;240m'
    waiting     = ESC + '1;38;2;67;63;155m'
    xtr         = ESC + '1;38;5;177m'

    # Color reset
    end         = ESC + '0m'
