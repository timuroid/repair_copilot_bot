from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI
from pydantic import BaseModel, Field

from app import gpt_service


load_dotenv()

app = FastAPI(
    title="Repair Copilot API",
    description="Stateless API: Chat and EndDialog using GPT with a JSON hypothesis tree.",
    version="2.0.0",
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("api.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)


# ===== DTOs =====

class MessagePair(BaseModel):
    user: str = Field(..., description="Сообщение пользователя")
    bot: str = Field(..., description="Ответ ассистента")


class ChatRequest(BaseModel):
    user_message: str = Field(..., description="Текущее сообщение пользователя")
    history: List[MessagePair] = Field(
        default_factory=list,
        description="Парная история в виде списка {user, bot}",
    )
    tree: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Текущее дерево гипотез (JSON). Оставьте пустым для нового диалога",
    )

    class Config:
        schema_extra = {
            "example": {
                "user_message": "Ноутбук греется и сильно шумит вентилятор",
                "history": [
                    {
                        "user": "Компьютер стал зависать после обновления драйверов",
                        "bot": "Понял. Замечали ли вы перегрев или троттлинг?",
                    }
                ],
                "tree": {
                    "title": "Диагностика производительности",
                    "status": "в работе",
                    "branches": [
                        {"name": "Симптомы", "hypotheses": []},
                        {"name": "Изменения", "hypotheses": []},
                        {"name": "Окружение", "hypotheses": []},
                        {"name": "Инструменты", "hypotheses": []},
                        {"name": "Ограничения", "hypotheses": []},
                    ],
                },
            }
        }


class ChatResponse(BaseModel):
    response: str = Field(..., description="Ответ ассистента пользователю")
    tree: Dict[str, Any] = Field(..., description="Обновлённое дерево гипотез (JSON)")

    class Config:
        schema_extra = {
            "example": {
                "response": "Похоже на перегрев. Проверьте пыль в системе охлаждения, затем запустите стресс‑тест с мониторингом температур (например, AIDA64). Сообщите максимальные температуры CPU/GPU.",
                "tree": {
                    "title": "Диагностика производительности",
                    "status": "в работе",
                    "branches": [
                        {
                            "name": "Симптомы",
                            "hypotheses": [
                                {
                                    "title": "Перегрев системы охлаждения",
                                    "status": "актуальна",
                                    "detection_method": "Проверка пыли и мониторинг температур под нагрузкой",
                                }
                            ],
                        }
                    ],
                },
            }
        }


class EndDialogRequest(BaseModel):
    history: List[MessagePair] = Field(
        default_factory=list,
        description="Вся история диалога (парные сообщения)",
    )
    tree: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Итоговое дерево гипотез (необязательно)",
    )

    class Config:
        schema_extra = {
            "example": {
                "history": [
                    {"user": "Не включается", "bot": "Проверьте кабель и БП."},
                    {"user": "Кабель исправен", "bot": "Измерьте напряжение БП."},
                ],
                "tree": {
                    "title": "Диагностика питания",
                    "status": "завершено",
                    "branches": [],
                },
            }
        }


class EndDialogResponse(BaseModel):
    summary: str = Field(..., description="Краткое резюме/рекомендации по диалогу")

    class Config:
        schema_extra = {
            "example": {
                "summary": "Проблема была в блоке питания: напряжение в норме под нагрузкой не держалось. Рекомендация — заменить БП; вторично проверить разъёмы питания и материнской платы.",
            }
        }


# ===== Routes =====

@app.post(
    "/chat",
    response_model=ChatResponse,
    tags=["chat"],
    summary="Чат: ответ и обновление дерева",
    description=(
        "Stateless чат. Передайте user_message, парную history и текущее tree (или пустое).\n"
        "Сервис вернёт ответ и обновлённое дерево. Дальше храните их у клиента."
    ),
)
def chat(req: ChatRequest) -> ChatResponse:
    new_tree = gpt_service.generate_hypotheses(
        user_message=req.user_message,
        chat_history=[pair.dict() for pair in req.history],
        tree=req.tree,
    )
    reply = gpt_service.generate_response(
        history=[pair.dict() for pair in req.history],
        user_message=req.user_message,
        tree=new_tree,
    )
    return ChatResponse(response=reply, tree=new_tree)


@app.post(
    "/end_dialog",
    response_model=EndDialogResponse,
    tags=["chat"],
    summary="Завершение диалога и резюме",
    description=(
        "Сформировать краткое резюме по всей истории диалога. Дерево опционально,"
        " используется только как контекст в клиентах."
    ),
)
def end_dialog(req: EndDialogRequest) -> EndDialogResponse:
    summary = gpt_service.generate_summary([pair.dict() for pair in req.history])
    return EndDialogResponse(summary=summary)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
