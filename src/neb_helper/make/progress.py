from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import sys
from typing import Optional


class TeeLog:
    def __init__(self, file_handle, screen_handle=None):
        self.file_handle = file_handle
        self.screen_handle = screen_handle or sys.stdout

    def write(self, text: str) -> int:
        self.file_handle.write(text)
        self.file_handle.flush()
        self.screen_handle.write(text)
        self.screen_handle.flush()
        return len(text)

    def flush(self) -> None:
        self.file_handle.flush()
        self.screen_handle.flush()

    def close(self) -> None:
        self.file_handle.close()


@contextmanager
def optimizer_logfile(logfile_path: Optional[str], log_to_screen) -> object:
    """Return a logfile target accepted by ASE optimizers.

    If screen logging is enabled and a file path is also provided, ASE writes to
    a small tee object so the same optimizer table goes to both places.
    """
    screen = bool_from_config(log_to_screen)
    if not screen:
        yield logfile_path
        return

    if logfile_path is None or logfile_path == "" or logfile_path == "-":
        yield "-"
        return

    path = Path(logfile_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("w", encoding="utf-8")
    try:
        yield TeeLog(handle)
    finally:
        handle.close()


def progress_print(enabled, message: str) -> None:
    if bool_from_config(enabled):
        print(message, flush=True)


def bool_from_config(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "1", "on"}:
            return True
        if lowered in {"false", "no", "0", "off", ""}:
            return False
    return bool(value)
