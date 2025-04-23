import os
import logging
from dotenv import load_dotenv
from fastapi import FastAPI
from pydantic import BaseModel
from app import db
from app import gpt_service

# Загружаем переменные окружения из .env
load_dotenv()

# Инициализируем FastAPI-приложение
app = FastAPI()

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("bot.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)

# Инициализация базы данных
db.init_db()

# Модель запроса пользователя
class UserMessage(BaseModel):
    user_id: int
    message: str

@app.post("/chat")
def chat_with_bot(user_message: UserMessage):
    history = db.fetch_dialog_history(user_message.user_id)
    response = gpt_service.generate_response(user_message.user_id, history, user_message.message)
    db.save_dialog_entry(user_message.user_id, user_message.message, response)
    return {"response": response}

@app.get("/check_dialog")
def check_dialog(user_id: int):
    return {"status": db.check_dialog_status(user_id)}

@app.post("/end_dialog")
def end_dialog(user_id: int):
    messages = db.finish_dialog(user_id)
    if not messages:
        return {"error": "Нет завершённых диалогов"}

    summary = gpt_service.generate_summary(messages)
    return {"message": "Диалог завершён", "summary": summary}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, workers=2)
