import logging
import os
import sys
import traceback

import requests

PROJECT_NAME = "PSUT Community Service Notifier"
NTFY_TOPIC_URL = "https://ntfy.sh/my_lubuntu_laptop"
MAX_DETAIL_LENGTH = 700

_original_excepthook = sys.excepthook
_hook_installed = False
_hook_source: str | None = None


def _shorten(text: str, max_length: int = MAX_DETAIL_LENGTH) -> str:
    text = " ".join(str(text).split())
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."


def notify_error(error: object, source: str | None = None, details: str | None = None):
    """Send a short error report to ntfy. Notification failures are ignored."""
    if isinstance(error, BaseException):
        error_name = type(error).__name__
        error_message = str(error)
    else:
        error_name = "Error"
        error_message = str(error)

    message_parts = [
        f"Project: {PROJECT_NAME}",
        f"Source: {source or 'unknown'}",
        f"{error_name}: {_shorten(error_message, 250)}",
    ]

    if details:
        message_parts.append(f"Details: {_shorten(details)}")

    try:
        requests.post(
            NTFY_TOPIC_URL,
            data="\n".join(message_parts).encode(encoding="utf-8"),
            timeout=5,
        )
    except Exception:
        pass


def install_exception_hook(source: str | None = None):
    """Report otherwise unhandled exceptions from standalone scripts."""
    global _hook_installed, _hook_source
    _hook_source = source or _hook_source
    if _hook_installed:
        return

    def _notify_excepthook(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            _original_excepthook(exc_type, exc_value, exc_traceback)
            return

        details = "".join(
            traceback.format_exception(exc_type, exc_value, exc_traceback, limit=4)
        )
        notify_error(exc_value, source=_hook_source, details=details)
        _original_excepthook(exc_type, exc_value, exc_traceback)

    sys.excepthook = _notify_excepthook
    _hook_installed = True


class NtfyErrorHandler(logging.Handler):
    """Logging handler that reports ERROR and CRITICAL records to ntfy."""

    def emit(self, record: logging.LogRecord):
        try:
            source = f"{record.name}:{os.path.basename(record.pathname)}:{record.lineno}"
            details = self.format(record)
            notify_error(record.getMessage(), source=source, details=details)
        except Exception:
            pass
