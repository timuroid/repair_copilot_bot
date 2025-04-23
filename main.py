import os
from openai import OpenAI
import sqlite3
import logging
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from datetime import datetime
from openai._exceptions import OpenAIError, RateLimitError
from app import db


# Загружаем переменные окружения из .env
load_dotenv()

# Настраиваем API-ключи
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("❌ API-ключ OpenAI не найден! Укажите его в файле .env")

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENAI_API_KEY,
    )

app = FastAPI()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("bot.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)




db.init_db()

class UserMessage(BaseModel):
    user_id: int
    message: str

def load_prompt(filename: str) -> str:
    base_dir = os.path.abspath(os.path.dirname(__file__))
    prompt_path = os.path.join(base_dir, "prompts", filename)
    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read()


SYSTEM_PROMPT_TEMPLATE = load_prompt("system_prompt.md")
HYPOTHESIS_SYSTEM_PROMPT = load_prompt("hypothesis_prompt.md")
SUMMARY_PROMPT_TEMPLATE = load_prompt("summary_prompt.md")
PROMPT_TEMPLATE = """


**История диалога:**
{history}

**Последнее сообщение пользователя:**
'{user_message}'   

🧩 **Гипотезы от второго генератора (для справки):**
{hypotheses}
"""


def generate_hypotheses(history: str, user_message: str) -> str:
    prompt = f"""
🗂 **История диалога (контекст):**
{history}

👷 **Последнее сообщение пользователя:**
"{user_message}"

📍 ВАЖНО:
- Сначала определи, на каком этапе анализа сейчас находится диалог (технический, внешний, организационный или управленческий).
- Сгенерируй 10 разнообразных гипотез, которые соответствуют этому этапу.
- Гипотезы пиши кратко, с нребольшими пояснениямий
"""

    response = client.chat.completions.create(
        model="deepseek/deepseek-chat-v3-0324",
        messages=[{"role": "system", "content": HYPOTHESIS_SYSTEM_PROMPT},
                  {"role": "user", "content": prompt}],
        temperature=0.6,
        
    )

    return response.choices[0].message.content.strip()



def get_gpt_response(user_id: int, message: str) -> str:
    history = db.fetch_dialog_history(user_id)
    formatted_history = "\n".join([f"👷 {msg}\n🤖 {resp}" for msg, resp in history])

    hypotheses = generate_hypotheses(formatted_history, message)
    print("\n🧠 Подсказки от аналитика:\n" + hypotheses + "\n" + "-"*50)

    prompt = PROMPT_TEMPLATE.format(history=formatted_history, user_message=message, hypotheses=hypotheses)

    try:
        response = client.chat.completions.create(
            model="deepseek/deepseek-chat-v3-0324",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT_TEMPLATE},
                {"role": "user", "content": prompt}
            ],
            temperature=0.6,
        )
        bot_reply = response.choices[0].message.content
        db.save_dialog_entry(user_id, message, bot_reply)
        return bot_reply
    except RateLimitError as e:
        logging.error(f"🚦 Превышен лимит: {e}")
        raise HTTPException(status_code=429, detail="Лимит OpenAI превышен.")
    except OpenAIError as e:
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
    return {"status": db.check_dialog_status(user_id)}

@app.post("/end_dialog")
def end_dialog(user_id: int):
    messages = db.finish_dialog(user_id)
    if not messages:
        return {"error": "Нет завершённых диалогов"}

    # 👇 Преобразуем историю диалога в читаемый текст
    formatted_history = "\n".join([
        f"👷 {msg}\n🤖 {resp}" for (_, msg, resp, _, _) in messages
    ])

    # 👇 Подставляем историю в шаблон
    summary_prompt = SUMMARY_PROMPT_TEMPLATE.format(messages=formatted_history)

    try:
        response = client.chat.completions.create(
            model="deepseek/deepseek-chat-v3-0324",
            messages=[{"role": "system", "content": summary_prompt}],
        )
        summary = response.choices[0].message.content
    except OpenAIError as e:
        logging.error(f"❌ Ошибка при генерации сводки: {e}")
        summary = f"Ошибка OpenAI: {str(e)}"
    except Exception as e:
        logging.error(f"⚠️ Общая ошибка генерации сводки: {e}")
        summary = f"Ошибка: {str(e)}"

    return {"message": "Диалог завершён", "summary": summary}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, workers=2)
