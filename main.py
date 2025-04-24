import os
import logging
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from app.db import DialogDB, MessageDB
from app import gpt_service
from app.gpt_service import clear_tree

# Загрузка переменных окружения
load_dotenv()

app = FastAPI()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("bot.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)

DialogDB.init()

class UserMessage(BaseModel):
    user_id: int
    message: str

@app.post("/force_end_dialog")
def force_end_dialog(user_id: int):
    dialog_id = DialogDB.get_active_dialog_id(user_id)
    if dialog_id:
        DialogDB.finish_dialog(user_id)
        clear_tree(user_id)
    return {"message": "Диалог завершён без генерации сводки"}


@app.post("/start_dialog")
def start_dialog(user_id: int):
    DialogDB.finish_dialog(user_id)
    clear_tree(user_id)
    dialog_id = DialogDB.create_dialog(user_id)
    return {"message": "Диалог инициализирован", "dialog_id": dialog_id}

@app.post("/chat")
def chat_with_bot(user_message: UserMessage):
    dialog_id = DialogDB.get_active_dialog_id(user_message.user_id)
    if not dialog_id:
        raise HTTPException(status_code=400, detail="Нет активного диалога. Сначала вызовите /start_dialog.")

    history = MessageDB.fetch_dialog_history(dialog_id)
    gpt_service.generate_hypotheses(user_message.user_id, user_message.message, history)
    response = gpt_service.generate_response(user_message.user_id, history, user_message.message)

    # 💾 Сохраняем роли корректно
    MessageDB.save(dialog_id, "user", user_message.message)
    MessageDB.save(dialog_id, "bot", response)

    return {"response": response}

@app.get("/check_dialog")
def check_dialog(user_id: int):
    dialog_id = DialogDB.get_active_dialog_id(user_id)
    return {"active": bool(dialog_id), "dialog_id": dialog_id}

from fastapi import HTTPException
from app.db import DialogDB, MessageDB  # Убедись, что MessageDB импортирован

@app.post("/end_dialog")
def end_dialog(user_id: int):
    dialog_id = DialogDB.get_active_dialog_id(user_id)
    if not dialog_id:
        raise HTTPException(status_code=400, detail="Нет активного диалога")

    history = MessageDB.fetch_dialog_history(dialog_id)
    if not history:
        raise HTTPException(status_code=400, detail="Нет сообщений в диалоге")

    DialogDB.finish_dialog(user_id)

    summary = gpt_service.generate_summary(history)
    return {"message": "Диалог завершён", "summary": summary}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, workers=2)
