import os
import openai
import sqlite3
import logging
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from datetime import datetime
import openai.error

# Загружаем переменные окружения из .env
load_dotenv()

# Настраиваем API-ключи
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("❌ API-ключ OpenAI не найден! Укажите его в файле .env")

openai.api_key = OPENAI_API_KEY

DB_PATH = "conversations.db"
ARCHIVE_DB_PATH = "history.db"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("bot.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)

app = FastAPI()

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

init_db()

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
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
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
                ],
                timeout=30
            )
            bot_reply = response["choices"][0]["message"]["content"]
            cursor.execute(
                "INSERT INTO dialogs (user_id, message, bot_response, status) VALUES (?, ?, ?, 'active')",
                (user_id, message, bot_reply)
            )
            conn.commit()
            return bot_reply
        except openai.error.Timeout as e:
            logging.error(f"⏳ Таймаут от OpenAI: {e}")
            raise HTTPException(status_code=504, detail="Таймаут от OpenAI.")
        except openai.error.RateLimitError as e:
            logging.error(f"🚦 Превышен лимит OpenAI: {e}")
            raise HTTPException(status_code=429, detail="Превышен лимит OpenAI.")
        except openai.error.OpenAIError as e:
            logging.error(f"❌ Ошибка OpenAI: {e}")
            raise HTTPException(status_code=500, detail="Ошибка OpenAI.")
        except Exception as e:
            logging.error(f"⚠️ Общая ошибка: {e}")
            raise HTTPException(status_code=500, detail="Непредвиденная ошибка.")

@app.post("/chat")
def chat_with_bot(user_message: UserMessage):
    return {"response": get_gpt_response(user_message.user_id, user_message.message)}

@app.get("/check_dialog")
def check_dialog(user_id: int):
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
        return {"error": "Нет завершённых диалогов"}

    # Копирование в архивную БД
    with sqlite3.connect(ARCHIVE_DB_PATH) as archive_conn:
        archive_cursor = archive_conn.cursor()
        archive_cursor.executemany(
            "INSERT INTO dialogs (user_id, message, bot_response, status, created_at) VALUES (?, ?, ?, ?, ?)",
            messages
        )
        archive_conn.commit()

    # Очистка из основной БД
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM dialogs WHERE user_id = ? AND status = 'finished'",
            (user_id,)
        )
        conn.commit()

    # Сводка
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
            messages=[{"role": "system", "content": summary_prompt}],
            timeout=30
        )
        summary = response["choices"][0]["message"]["content"]
    except openai.error.Timeout as e:
        logging.error(f"⏳ Таймаут при генерации сводки: {e}")
        summary = "Ошибка: превышено время ожидания."
    except openai.error.OpenAIError as e:
        logging.error(f"❌ Ошибка при генерации сводки: {e}")
        summary = f"Ошибка OpenAI: {str(e)}"
    except Exception as e:
        logging.error(f"⚠️ Общая ошибка генерации сводки: {e}")
        summary = f"Ошибка: {str(e)}"

    return {"message": "Диалог завершён", "summary": summary}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, workers=2)
