import sqlite3

DB_PATH = "history.db"

def view_all_dialogs():
    """Выводит всю историю общения пользователей с ботом"""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM dialogs")
        rows = cursor.fetchall()

        if not rows:
            print("📭 В базе данных нет записей.")
            return

        print("\n📜 ВСЕ ДИАЛОГИ:\n")
        for row in rows:
            print(f"🆔 ID: {row[0]}")
            print(f"👤 Пользователь ID: {row[1]}")
            print(f"👷 Сообщение: {row[2]}")
            print(f"🤖 Ответ бота: {row[3]}")
            print(f"📌 Статус: {row[4]}")
            print(f"⏳ Время: {row[5]}")
            print("-" * 50)

# Запускаем просмотр базы
view_all_dialogs()

