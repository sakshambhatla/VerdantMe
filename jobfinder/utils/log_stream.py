"""Centralized log capture — writes to Rich console, log file, and SSE ring buffer.

The SSE ring buffer is skipped in managed mode (SUPABASE_URL set) since the
log stream endpoint is disabled to prevent cross-user data leakage.
"""
from __future__ import annotations

import contextvars
import json
import os
import re
import sys
import threading
from collections import deque
from datetime import datetime
from pathlib import Path

# ── Run ID context (auto-propagated to threads by asyncio.to_thread) ─────

_current_run_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "_current_run_id", default=None
)


def set_run_context(run_id: str | None) -> None:
    """Set the active job-run ID for the current context.

    All subsequent ``log()`` calls in this context (including threads spawned
    by ``asyncio.to_thread``) will be tagged with this run ID.
    """
    _current_run_id.set(run_id)

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


def init_log_stream(data_dir: Path) -> Path | None:
    """Create the log directory and open a timestamped log file.

    Called once from the FastAPI lifespan() at startup.  Returns the file path,
    or None in managed/cloud mode where file I/O is skipped (stdout captured by Render).
    """
    global _log_file_path
    if os.environ.get("SUPABASE_URL"):
        return None  # Cloud: skip file I/O; stdout is captured by the container host
    log_dir = data_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    _log_file_path = log_dir / f"server_{timestamp}.log"
    _log_file_path.touch()
    return _log_file_path


def log(message: str, level: str = "info", *, run_id: str | None = None) -> None:
    """Log a message to Rich console, log file, AND the SSE ring buffer.

    Args:
        message: Rich-formatted string (markup preserved for console output).
        level: One of ``"info"``, ``"success"``, ``"warning"``, ``"error"``.
        run_id: Explicit run ID override.  Falls back to the contextvar set
                via ``set_run_context()``.
    """
    global _log_counter

    effective_run_id = run_id or _current_run_id.get(None)

    # 1. Console output — structured JSON in cloud mode, Rich locally
    _is_cloud = bool(os.environ.get("SUPABASE_URL"))
    if not _is_cloud:
        from jobfinder.utils.display import console
        console.print(message)

    # 2. Strip Rich markup for plain text destinations
    plain = strip_rich_markup(message).strip()
    if not plain:
        return

    timestamp = datetime.now().strftime("%H:%M:%S")

    # 2b. Structured JSON to stdout in cloud mode (parsed by log stream providers)
    if _is_cloud:
        json_entry: dict[str, str] = {
            "timestamp": datetime.now().isoformat(),
            "level": level,
            "message": plain,
        }
        if effective_run_id:
            json_entry["run_id"] = effective_run_id
        print(json.dumps(json_entry), file=sys.stdout, flush=True)

    # 3. Write to log file (thread-safe)
    if _log_file_path is not None:
        prefix = f"[{timestamp}] [{level.upper()}]"
        if effective_run_id:
            prefix += f" [run:{effective_run_id[:8]}]"
        with _file_lock:
            with open(_log_file_path, "a") as f:
                f.write(f"{prefix} {plain}\n")

    # 4. Push to ring buffer (thread-safe)
    # Access controlled at the endpoint level (devtest+ only, see routes/logs.py)
    with _log_lock:
        entry = {
            "seq": _log_counter,
            "timestamp": timestamp,
            "level": level,
            "message": plain,
            "run_id": effective_run_id,
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


def get_logs_for_run(run_id: str) -> list[dict]:
    """Return all buffered log entries tagged with *run_id*."""
    with _log_lock:
        return [e for e in _log_buffer if e.get("run_id") == run_id]
