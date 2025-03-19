import os
import openai
import sqlite3
import logging
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from datetime import datetime

# Загружаем переменные окружения из .env
load_dotenv()

# Настраиваем API-ключи
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("❌ API-ключ OpenAI не найден! Укажите его в файле .env")

openai.api_key = OPENAI_API_KEY

# Подключение к базе данных SQLite
DB_PATH = "conversations.db"

# Настройка логирования
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Инициализация FastAPI
app = FastAPI()

# Создаём таблицу, если её нет
def init_db():
    with sqlite3.connect(DB_PATH) as conn:
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
        logging.info("✅ База данных инициализирована.")

init_db()

# Определяем модель данных
class UserMessage(BaseModel):
    user_id: int
    message: str

SYSTEM_PROMPT_TEMPLATE = """
Ты – виртуальный помощник для инженеров и ремонтных специалистов. Твоя задача – помогать пользователям выявлять корневые причины поломок оборудования, используя метод "5 почему". 
Язык общения - "Русский"

📌 **Как вести беседу:**  
1️⃣ **Сбор информации и первая гипотеза**  
   - Спросите: **"Опишите проблему: когда заметили неисправность и что именно не так?"**  
   - Если пользователь уже упомянул **причину поломки**, сразу переходите к **"Почему?"**, **не формируя отдельный список гипотез**.  
   - Если причина неочевидна, предложите **2-3 гипотезы + сразу задайте "Почему?"**, чтобы направить анализ в нужное русло.  

2️⃣ **Глубокий анализ "5 почему"**  
   - Бесконечно углубляйтесь в цепочку "почему?", пока пользователь сам не решит остановиться.  
   - **Не повторяйте вопросы**, если ответ уже был дан в диалоге.  
   - Если пользователь даёт общий ответ, уточните: **"Что именно могло привести к этой причине?"**  
   - Если возможны несколько направлений анализа, предложите **2-3 варианта и попросите выбрать самый вероятный.**  

3️⃣ **Форматирование сообщений**  
   - Используйте **списки, выделение, чёткую структуру текста**.  
   - **Каждое сообщение должно быть удобочитаемым**, избегайте длинных неструктурированных абзацев.  

4️⃣ **Примеры общения**  

сообщение от пользователь - 'Прокатный стан даёт кривые листы.'  
сообщение от бот - 'Когда впервые заметили проблему? Проявляется на всех листах или только на некоторых?'  

сообщение от пользователь - 'Вчера, но не на всех листах.'  
сообщение от бот - 'Возможные причины:  
   1️⃣ Неравномерный износ валков.  
   2️⃣ Проблемы с подачей металла.  
   3️⃣ Изменения в температуре нагрева.  
Почему это могло произойти? Какие изменения были в работе оборудования?'  

сообщение от пользователь - 'Температура повысилась, стан работал на максимальной нагрузке.'  
сообщение от бот - 'Почему температура могла повыситься? Возможно, система охлаждения работает нестабильно?'  

5️⃣ **Завершение диалога**  
   - Бот **никогда не завершает диалог сам**, если пользователь не напишет **"Проблема решена"**.  
   - Когда пользователь решает проблему, бот кратко подводит итог:  
     **"Корневая причина: [указать причину]. Проверьте [что нужно сделать] в будущем, чтобы избежать повторения."**  
   - **Не пересказывать всю историю** в конце, только суть.  
"""

PROMPT_TEMPLATE = """
{history}
сообщение от пользователя '{user_message}'   
"""

def get_gpt_response(user_id: int, message: str) -> str:
    """Запрашивает ответ у OpenAI и сохраняет историю в базе SQLite."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()

        # Получаем историю общения пользователя
        cursor.execute(
            "SELECT message, bot_response FROM dialogs WHERE user_id = ? AND status = 'active'",
            (user_id,)
        )
        history = cursor.fetchall()

        formatted_history = "\n".join([f"👷 {msg}\n🤖 {resp}" for msg, resp in history])
        prompt = PROMPT_TEMPLATE.format(history=formatted_history, user_message=message)

        try:
            response = openai.ChatCompletion.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT_TEMPLATE},
                    {"role": "user", "content": prompt}
                ]
            )
            bot_reply = response["choices"][0]["message"]["content"]

            # Сохраняем в базу данных
            cursor.execute(
                "INSERT INTO dialogs (user_id, message, bot_response, status) VALUES (?, ?, ?, 'active')",
                (user_id, message, bot_reply)
            )
            conn.commit()

            return bot_reply
        except Exception as e:
            logging.error(f"Ошибка при запросе к OpenAI: {e}")
            raise HTTPException(status_code=500, detail="Ошибка обработки запроса к OpenAI.")

@app.post("/chat")
def chat_with_bot(user_message: UserMessage):
    """Обрабатывает сообщение пользователя и сохраняет историю в базе данных."""
    return {"response": get_gpt_response(user_message.user_id, user_message.message)}

@app.get("/check_dialog")
def check_dialog(user_id: int):
    """Проверяет, есть ли у пользователя активный диалог."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM dialogs WHERE user_id = ? AND status = 'active'",
            (user_id,)
        )
        active_dialogs = cursor.fetchone()[0]

    return {"status": "active" if active_dialogs > 0 else "not_found"}

@app.post("/end_dialog")
def end_dialog(user_id: int):
    """Завершает текущий диалог и создаёт сводку."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()

        cursor.execute(
            "UPDATE dialogs SET status = 'finished' WHERE user_id = ? AND status = 'active'",
            (user_id,)
        )
        conn.commit()

        # Получаем историю сообщений
        cursor.execute(
            "SELECT message, bot_response FROM dialogs WHERE user_id = ? AND status = 'finished'",
            (user_id,)
        )
        messages = cursor.fetchall()

    if not messages:
        return {"error": "Нет завершённых диалогов"}

    summary_prompt = f"""
    Вот история диалога с пользователем:
    {messages}

    Составь краткую сводку:
    - Какая была замечена проблема?
    - Что было проверено?
    - Какая была выявлена корневая причина?
    """

    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[{"role": "system", "content": summary_prompt}]
        )
        summary = response["choices"][0]["message"]["content"]
    except Exception as e:
        summary = f"Ошибка при генерации сводки: {str(e)}"

    return {"message": "Диалог завершён", "summary": summary}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, workers=2)
