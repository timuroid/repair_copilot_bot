# app/db.py

import sqlite3
import logging
from typing import List, Tuple, Any

DB_PATH = "data/conversations.db"
ARCHIVE_DB_PATH = "data/history.db"

def init_db():
    for db in [DB_PATH, ARCHIVE_DB_PATH]:
        with sqlite3.connect(db) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS dialogs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    message TEXT,
                    bot_response TEXT,
                    status TEXT DEFAULT "active",
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.commit()
            logging.info(f"✅ База данных инициализирована: {db}")

def fetch_dialog_history(user_id: int) -> List[Tuple[str, str]]:
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT message, bot_response FROM dialogs WHERE user_id = ? AND status = 'active'",
            (user_id,)
        )
        return cursor.fetchall()

def save_dialog_entry(user_id: int, message: str, bot_response: str) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO dialogs (user_id, message, bot_response, status) VALUES (?, ?, ?, 'active')",
            (user_id, message, bot_response)
        )
        conn.commit()

def check_dialog_status(user_id: int) -> str:
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM dialogs WHERE user_id = ? AND status = 'active'",
            (user_id,)
        )
        active_dialogs = cursor.fetchone()[0]
        return "active" if active_dialogs > 0 else "not_found"

def finish_dialog(user_id: int) -> List[Tuple[Any]]:
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE dialogs SET status = 'finished' WHERE user_id = ? AND status = 'active'",
            (user_id,)
        )
        conn.commit()

        cursor.execute(
            "SELECT user_id, message, bot_response, status, created_at FROM dialogs WHERE user_id = ? AND status = 'finished'",
            (user_id,)
        )
        messages = cursor.fetchall()

    if not messages:
        return []

    with sqlite3.connect(ARCHIVE_DB_PATH) as archive_conn:
        archive_cursor = archive_conn.cursor()
        archive_cursor.executemany(
            "INSERT INTO dialogs (user_id, message, bot_response, status, created_at) VALUES (?, ?, ?, ?, ?)",
            messages
        )
        archive_conn.commit()

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM dialogs WHERE user_id = ? AND status = 'finished'",
            (user_id,)
        )
        conn.commit()

    return messages
