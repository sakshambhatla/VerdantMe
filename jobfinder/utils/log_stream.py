"""Centralized log capture — writes to Rich console, log file, and SSE ring buffer."""
from __future__ import annotations

import re
import threading
from collections import deque
from datetime import datetime
from pathlib import Path

# ── Ring buffer (thread-safe reads via lock) ────────────────────────────────

_log_buffer: deque[dict] = deque(maxlen=2000)
_log_counter: int = 0
_log_lock = threading.Lock()

# ── Log file (set once at server startup) ───────────────────────────────────

_log_file_path: Path | None = None
_file_lock = threading.Lock()

# ── Rich markup stripper ────────────────────────────────────────────────────

_RICH_TAG_RE = re.compile(r"\[/?[a-zA-Z_/ ]+\]")


def strip_rich_markup(text: str) -> str:
    """Remove Rich console markup tags like [bold], [green], [/dim], etc."""
    return _RICH_TAG_RE.sub("", text)


# ── Public API ──────────────────────────────────────────────────────────────


def init_log_stream(data_dir: Path) -> Path:
    """Create the log directory and open a timestamped log file.

    Called once from the FastAPI lifespan() at startup.  Returns the file path.
    """
    global _log_file_path
    log_dir = data_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    _log_file_path = log_dir / f"server_{timestamp}.log"
    _log_file_path.touch()
    return _log_file_path


def log(message: str, level: str = "info") -> None:
    """Log a message to Rich console, log file, AND the SSE ring buffer.

    Args:
        message: Rich-formatted string (markup preserved for console output).
        level: One of ``"info"``, ``"success"``, ``"warning"``, ``"error"``.
    """
    global _log_counter

    # 1. Console output (unchanged Rich behaviour)
    from jobfinder.utils.display import console

    console.print(message)

    # 2. Strip Rich markup for plain text destinations
    plain = strip_rich_markup(message).strip()
    if not plain:
        return

    timestamp = datetime.now().strftime("%H:%M:%S")

    # 3. Write to log file (thread-safe)
    if _log_file_path is not None:
        with _file_lock:
            with open(_log_file_path, "a") as f:
                f.write(f"[{timestamp}] [{level.upper()}] {plain}\n")

    # 4. Push to ring buffer (thread-safe)
    with _log_lock:
        entry = {
            "seq": _log_counter,
            "timestamp": timestamp,
            "level": level,
            "message": plain,
        }
        _log_buffer.append(entry)
        _log_counter += 1


def get_logs_since(seq: int) -> tuple[list[dict], int]:
    """Return all log entries with ``seq >= seq`` and the current counter.

    Each SSE client tracks its own ``last_seen_seq`` and calls this to get
    only new entries.  Thread-safe for concurrent readers.
    """
    with _log_lock:
        entries = [e for e in _log_buffer if e["seq"] >= seq]
        return entries, _log_counter


def get_current_seq() -> int:
    """Return the current sequence counter (for initialising a new SSE client)."""
    with _log_lock:
        return _log_counter
