import os
import json
from datetime import datetime
from dotenv import load_dotenv
from app.db import DialogDB, MessageDB
from app.gpt_service import (
    clear_tree,
    generate_hypotheses,
    generate_response,
    generate_summary,
    _format_history,
    get_tree
)

# === Загрузка переменных окружения
load_dotenv()

# === Константы
TEST_USER_ID = 9999
LOG_FILE = "chat_debug.log"

# === Подготовка лог-файла
def log(*args):
    text = " ".join(str(a) for a in args)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(text + "\n")
    print(text)  # чтобы видеть ещё и в консоли

# === Очистка всего
clear_tree(TEST_USER_ID)
DialogDB.finish_dialog(TEST_USER_ID)
dialog_id = DialogDB.create_dialog(TEST_USER_ID)

history = []

# === Начало
log("\n" + "="*60)
log(f"🕐 Старт симуляции: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
log("="*60)

print("\n🧪 Терминальный режим GPT-бота (выйти: /end)\n")

while True:
    user_input = input("👷 Вы: ").strip()

    if user_input.lower() == "/end":
        log("\n🔚 Завершение диалога.")
        DialogDB.finish_dialog(TEST_USER_ID)
        summary = generate_summary(history)
        log("\n📋 Сводка:")
        log(summary)
        break

    if not user_input:
        continue

    # === Отладка истории
    log("\n📤 [PROMPT] История на вход:")
    log(_format_history(history))
    log("📤 [PROMPT] Сообщение пользователя:", user_input)

    # === Генерация гипотез
    hypotheses = generate_hypotheses(TEST_USER_ID, user_input, history)
    log("\n🧠 Гипотезы (JSON):")
    log(json.dumps(hypotheses, indent=2, ensure_ascii=False))

    # === Дерево
    log("\n🌳 Обновлённое дерево:")
    log(json.dumps(get_tree(TEST_USER_ID), indent=2, ensure_ascii=False))

    # === Ответ
    response = generate_response(TEST_USER_ID, history, user_input)
    log("\n🤖 Ответ бота:")
    log(response.strip())

    # === История
    updated_history = history + [(user_input, response)]
    log("\n📚 Обновлённая история:")
    log(_format_history(updated_history))

    # === Сохраняем
    MessageDB.save(dialog_id, "user", user_input)
    MessageDB.save(dialog_id, "bot", response)
    history.append((user_input, response))

    print("-" * 60)