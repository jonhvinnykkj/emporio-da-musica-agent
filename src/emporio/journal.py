"""Append-only JSONL log of messages and handoffs, with contact data masked."""

import json
import re
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
# Digits with the usual separators; anything with fewer than 8 digits (prices, order numbers) is left alone.
PHONE = re.compile(r"(?<!\d)\+?\(?\d[\d\s().-]{5,}\d")
MIN_PHONE_DIGITS = 8
KEPT_DIGITS = 4


def _mask_phone(match: re.Match[str]) -> str:
    digits = re.sub(r"\D", "", match.group())
    return f"***{digits[-KEPT_DIGITS:]}" if len(digits) >= MIN_PHONE_DIGITS else match.group()


def mask_contact(text: str) -> str:
    """Replace e-mails with '***' and keep only the last 4 digits of phone numbers."""
    return PHONE.sub(_mask_phone, EMAIL.sub("***", text))


def _mask(value: Any) -> Any:
    if isinstance(value, str):
        return mask_contact(value)
    if isinstance(value, dict):
        return {key: _mask(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_mask(item) for item in value]
    return value


class Journal:
    """One JSON line per event. A write failure is swallowed: logging never stops a conversation."""

    def __init__(self, path: Path | None):
        self.path = path
        self._lock = threading.Lock()

    def record(self, kind: str, session_id: str, payload: dict[str, Any]) -> None:
        if self.path is None:
            return
        event = {
            "ts": datetime.now(UTC).isoformat(timespec="seconds"),
            "kind": kind,
            "session_id": session_id,
            "payload": _mask(payload),
        }
        try:
            line = json.dumps(event, ensure_ascii=False, default=str)
            with self._lock:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with self.path.open("a", encoding="utf-8") as file:
                    file.write(line + "\n")
        except OSError:
            pass
