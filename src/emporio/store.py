"""SQLite persistence: conversation text, support tickets and failed identity checks."""

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS tickets (
    id INTEGER PRIMARY KEY,
    session_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    summary TEXT NOT NULL,
    contact TEXT,
    order_id INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS failed_checks (
    id INTEGER PRIMARY KEY,
    session_id TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""
HISTORY_LIMIT = 20


class Store:
    def __init__(self, path: Path | str = ":memory:"):
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.executescript(SCHEMA)

    def history(self, session_id: str) -> list[dict]:
        """Last messages as plain text. A window may not start on an assistant turn."""
        rows = self.db.execute(
            "SELECT role, content FROM messages WHERE session_id = ? ORDER BY id DESC LIMIT ?",
            (session_id, HISTORY_LIMIT),
        ).fetchall()
        messages = [{"role": role, "content": content} for role, content in reversed(rows)]
        while messages and messages[0]["role"] != "user":
            messages.pop(0)
        return messages

    def add_exchange(self, session_id: str, user_text: str, assistant_text: str) -> None:
        with self.db:
            self.db.executemany(
                "INSERT INTO messages (session_id, role, content) VALUES (?, ?, ?)",
                [(session_id, "user", user_text), (session_id, "assistant", assistant_text)],
            )

    def create_ticket(
        self, session_id: str, kind: str, summary: str, contact: str | None, order_id: int | None
    ) -> str:
        with self.db:
            cursor = self.db.execute(
                "INSERT INTO tickets (session_id, kind, summary, contact, order_id) VALUES (?, ?, ?, ?, ?)",
                (session_id, kind, summary, contact, order_id),
            )
        return f"EM-{cursor.lastrowid:05d}"

    def record_failed_check(self, session_id: str) -> None:
        with self.db:
            self.db.execute("INSERT INTO failed_checks (session_id) VALUES (?)", (session_id,))

    def failed_checks(self, session_id: str) -> int:
        row = self.db.execute(
            "SELECT COUNT(*) FROM failed_checks WHERE session_id = ?", (session_id,)
        ).fetchone()
        return row[0]
