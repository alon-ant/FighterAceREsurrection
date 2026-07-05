#!/usr/bin/env python3
r"""
fa_logging.py  — drop-in logging upgrade for the Fighter Ace LAN server.

WHY
  The server currently does  `python "fa with web server.py" > server.log`, which
  gives one ever-growing flat file, nothing visible live while redirected, no
  survival across restarts, and high-frequency tags (POST-AUTH, telemetry) bury
  the one line that matters. This module replaces the single `log(tag,msg)`
  function WITHOUT touching the 200+ call sites.

WHAT YOU GET
  * Levels per line, inferred from the tag (ERROR/RELDROP/STALL → WARNING/ERROR;
    TX/RX/telemetry → DEBUG; everything else INFO) or set explicitly:
        log('DB', 'saved', level='DEBUG')
  * Console: colored, level-filtered (default INFO+), so the live view is readable.
  * Files (in ./logs, rotating, survive restarts, timestamped by run):
        logs/server.log        — everything at file level (default DEBUG), rotating
        logs/server.err.log    — WARNING+ only, so failures are instantly findable
        logs/run_*.log         — a per-run snapshot
  * A ring buffer of the last N lines that the web server can read for a live
    on-screen console (get_recent_logs()).
  * Full tracebacks: call  logx('TAG', 'context')  inside an except block and the
    stack is captured to file automatically.
  * Runtime control from the console: loglevel console <LEVEL>, logmute <TAG>,
    logunmute <TAG>, logtags — wired in the patch.

INSTALL  (see fa_logging_patch.txt for the exact edits)
"""
import os, sys, time, threading, logging, logging.handlers, collections, traceback
from datetime import datetime

# ── level inference by tag ────────────────────────────────────────────────────
# Tags are matched by prefix so 'TX/RELIABLE', 'TX/UNREL' etc. all fold to TX.
_TAG_LEVELS = {
    'ERROR': logging.ERROR, 'RELDROP': logging.WARNING, 'STALL-WATCH': logging.WARNING,
    'RX/DROP': logging.WARNING, 'REAP': logging.WARNING,
    'TX': logging.DEBUG, 'RX': logging.DEBUG, 'RELAY': logging.DEBUG,
    'SIM13': logging.DEBUG, 'GAMEDEF212': logging.DEBUG, 'GDFDUMP': logging.DEBUG,
    'POST-AUTH': logging.DEBUG, 'COMPOUND': logging.DEBUG, 'RELRX': logging.DEBUG,
}
_DEFAULT_LEVEL = logging.INFO

def _level_for(tag):
    if tag in _TAG_LEVELS:
        return _TAG_LEVELS[tag]
    head = tag.split('/', 1)[0]
    return _TAG_LEVELS.get(head, _DEFAULT_LEVEL)

# ── ANSI colour for the live console ──────────────────────────────────────────
_COLOR = {
    logging.DEBUG: '\033[90m',    # grey
    logging.INFO: '\033[0m',      # default
    logging.WARNING: '\033[33m',  # yellow
    logging.ERROR: '\033[31m',    # red
}
_RESET = '\033[0m'

# enable ANSI on Windows 10+ consoles; harmless elsewhere
def _enable_win_ansi():
    if os.name == 'nt':
        try:
            import ctypes
            k = ctypes.windll.kernel32
            k.SetConsoleMode(k.GetStdHandle(-11), 7)  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
        except Exception:
            pass

# ── ring buffer for the web live console ──────────────────────────────────────
_RING_MAX = 2000
_ring = collections.deque(maxlen=_RING_MAX)
_ring_lock = threading.Lock()

def get_recent_logs(n=200, min_level='DEBUG'):
    """Return the last n formatted log lines (newest last) at >= min_level.
    Safe to call from the web-server thread."""
    lvl = logging.getLevelName(min_level) if isinstance(min_level, str) else min_level
    if not isinstance(lvl, int): lvl = logging.DEBUG
    with _ring_lock:
        items = [t for t in _ring if t[0] >= lvl]
    return [t[1] for t in items[-n:]]

# ── runtime-mutable filter state ──────────────────────────────────────────────
_muted_tags = set()
_state_lock = threading.Lock()

class _ConsoleFilter(logging.Filter):
    def filter(self, rec):
        with _state_lock:
            return getattr(rec, 'fa_tag', '') not in _muted_tags

# ── the logging objects ───────────────────────────────────────────────────────
_logger = None
_console_handler = None
_initialised = False

def init_logging(log_dir='logs', console_level='INFO', file_level='DEBUG',
                 run_tagged=True):
    """Create handlers. Idempotent. Call once at startup BEFORE the first log()."""
    global _logger, _console_handler, _initialised
    if _initialised:
        return _logger
    _enable_win_ansi()
    os.makedirs(log_dir, exist_ok=True)

    _logger = logging.getLogger('fa')
    _logger.setLevel(logging.DEBUG)
    _logger.propagate = False

    # plain formatter (files) — the tag/timestamp are baked into the message by log()
    plain = logging.Formatter('%(message)s')

    # main rotating file: everything at file_level, 10 MB x 8 = ~80 MB history
    main_path = os.path.join(log_dir, 'server.log')
    fh = logging.handlers.RotatingFileHandler(
        main_path, maxBytes=10 * 1024 * 1024, backupCount=8, encoding='utf-8')
    fh.setLevel(getattr(logging, file_level, logging.DEBUG))
    fh.setFormatter(plain)
    _logger.addHandler(fh)

    # error file: WARNING+ only, so a crash is one glance away
    eh = logging.handlers.RotatingFileHandler(
        os.path.join(log_dir, 'server.err.log'), maxBytes=4 * 1024 * 1024,
        backupCount=4, encoding='utf-8')
    eh.setLevel(logging.WARNING)
    eh.setFormatter(plain)
    _logger.addHandler(eh)

    # per-run snapshot (survives restarts as its own file), only if requested
    if run_tagged:
        run_name = datetime.now().strftime('run_%Y%m%d_%H%M%S.log')
        rh = logging.FileHandler(os.path.join(log_dir, run_name), encoding='utf-8')
        rh.setLevel(getattr(logging, file_level, logging.DEBUG))
        rh.setFormatter(plain)
        _logger.addHandler(rh)

    # console handler — colored, level-filtered, mutable
    _console_handler = logging.StreamHandler(stream=sys.stdout)
    _console_handler.setLevel(getattr(logging, console_level, logging.INFO))
    _console_handler.addFilter(_ConsoleFilter())

    class _ColorFmt(logging.Formatter):
        def format(self, rec):
            base = rec.getMessage()
            try:
                tty = sys.stdout.isatty()
            except Exception:
                tty = False
            if tty:
                return _COLOR.get(rec.levelno, '') + base + _RESET
            return base
    _console_handler.setFormatter(_ColorFmt())
    _logger.addHandler(_console_handler)

    _initialised = True
    return _logger


def log(tag, msg, level=None):
    """Drop-in replacement for the server's original log(tag, msg).
    Formats identically ([HH:MM:SS.mmm][TAG            ] msg) and fans out to
    console (filtered) + files + ring buffer. `level` optional: 'DEBUG'..'ERROR'."""
    if not _initialised:
        init_logging()
    n = datetime.now()
    ts = n.strftime('%H:%M:%S.') + f'{n.microsecond // 1000:03d}'
    line = f'[{ts}][{tag:<16s}] {msg}'
    if level is None:
        lvl = _level_for(tag)
    else:
        lvl = getattr(logging, level.upper(), _DEFAULT_LEVEL) if isinstance(level, str) else level
    with _ring_lock:
        _ring.append((lvl, line))
    rec = _logger.makeRecord('fa', lvl, __file__, 0, line, None, None)
    rec.fa_tag = tag
    _logger.handle(rec)


def logx(tag, msg):
    """Like log() but ALSO appends the current exception traceback (to files).
    Use inside an `except` block:  except Exception: logx('DB','room save failed')."""
    log(tag, msg, level='ERROR')
    tb = traceback.format_exc()
    if tb and 'NoneType: None' not in tb:
        for tline in tb.rstrip().splitlines():
            log(tag, '    ' + tline, level='ERROR')


# ── runtime controls (wire to console commands) ───────────────────────────────
def set_console_level(level):
    if _console_handler:
        _console_handler.setLevel(getattr(logging, level.upper(), logging.INFO))
        return True
    return False

def mute_tag(tag):
    with _state_lock: _muted_tags.add(tag)

def unmute_tag(tag):
    with _state_lock: _muted_tags.discard(tag)

def list_muted():
    with _state_lock: return sorted(_muted_tags)
