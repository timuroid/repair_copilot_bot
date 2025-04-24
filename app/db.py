# db.py
import sqlite3
from contextlib import contextmanager
from typing import Optional, List, Tuple
from datetime import datetime

DB_PATH = "data/conversations.db"

@contextmanager
def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # удобство при доступе к колонкам
    try:
        yield conn
    finally:
        conn.commit()
        conn.close()


class DialogDB:
    @staticmethod
    def init():
        with get_connection() as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS dialogs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    status TEXT DEFAULT 'active',
                    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    finished_at TIMESTAMP
                )
            ''')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    dialog_id INTEGER NOT NULL,
                    role TEXT CHECK(role IN ('user', 'bot')) NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(dialog_id) REFERENCES dialogs(id)
                )
            ''')

    @staticmethod
    def create_dialog(user_id: int) -> int:
        with get_connection() as conn:
            cur = conn.execute(
                "INSERT INTO dialogs (user_id) VALUES (?)",
                (user_id,)
            )
            return cur.lastrowid

    @staticmethod
    def get_active_dialog_id(user_id: int) -> Optional[int]:
        with get_connection() as conn:
            cur = conn.execute(
                "SELECT id FROM dialogs WHERE user_id = ? AND status = 'active'",
                (user_id,)
            )
            row = cur.fetchone()
            return row["id"] if row else None

    @staticmethod
    def finish_dialog(user_id: int):
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE dialogs
                SET status = 'finished', finished_at = ?
                WHERE user_id = ? AND status = 'active'
                """,
                (datetime.now(), user_id)
            )

    @staticmethod
    def get_dialog_messages(dialog_id: int) -> List[Tuple[str, str]]:
        with get_connection() as conn:
            cur = conn.execute(
                "SELECT role, content FROM messages WHERE dialog_id = ? ORDER BY created_at",
                (dialog_id,)
            )
            return [(row["role"], row["content"]) for row in cur.fetchall()]


class MessageDB:
    @staticmethod
    def save(dialog_id: int, role: str, content: str):
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO messages (dialog_id, role, content)
                VALUES (?, ?, ?)
                """,
                (dialog_id, role, content)
            )

    @staticmethod
    def fetch_dialog_history(dialog_id: int) -> List[Tuple[str, str]]:
        with get_connection() as conn:
            cur = conn.execute(
                "SELECT role, content FROM messages WHERE dialog_id = ? ORDER BY created_at",
                (dialog_id,)
            )
            rows = cur.fetchall()

        # Формируем пары: (user -> bot)
        history = []
        user_msg = None
        for row in rows:
            if row["role"] == "user":
                user_msg = row["content"]
            elif row["role"] == "bot" and user_msg:
                history.append((user_msg, row["content"]))
                user_msg = None
        return history
