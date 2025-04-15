import logging
import os
import httpx
import re
from dotenv import load_dotenv
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ConversationHandler, ContextTypes, filters
)

load_dotenv()

# URL сервера FastAPI
API_URL = os.getenv("API_URL")

# Логирование
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("bot.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# Определяем состояния диалога
CHOOSING, TYPING_REPLY = range(2)

# Функция для преобразования Markdown в HTML
def convert_markdown_to_html(text: str) -> str:
    """Конвертирует Markdown-разметку от ChatGPT в HTML-разметку для Telegram."""
    text = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", text)  # **Жирный текст** → <b>Жирный текст</b>
    text = re.sub(r"\*(.*?)\*", r"<i>\1</i>", text)  # *Курсив* → <i>Курсив</i>
    text = re.sub(r"\n- ", r"\n• ", text)  # Преобразуем списки (Markdown → HTML-friendly)
    return text

def get_inline_keyboard():
    keyboard = [[InlineKeyboardButton("✅ Проблема решена", callback_data="end_dialog")]]
    return InlineKeyboardMarkup(keyboard)

# Асинхронный обработчик команды /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("Разобраться с проблемой", callback_data="start_dialog")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "Добро пожаловать! Нажмите кнопку ниже, чтобы начать разбираться с проблемой.",
        reply_markup=reply_markup,
        parse_mode="HTML"
    )
    return CHOOSING

# Асинхронный обработчик начала диалога
async def start_dialog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id
    else:
        user_id = update.effective_user.id

    timeout = httpx.Timeout(120.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            response = await client.post(f"{API_URL}/chat", json={"user_id": user_id, "message": ""})
            response.raise_for_status()

            if update.callback_query:
                await query.edit_message_text(
                    text="Диалог начат. Опишите вашу проблему.",
                    reply_markup=get_inline_keyboard(),
                    parse_mode="HTML"
                )
            else:
                await update.message.reply_text(
                    "Диалог начат. Опишите вашу проблему.",
                    reply_markup=get_inline_keyboard(),
                    parse_mode="HTML"
                )

            return TYPING_REPLY
        except httpx.TimeoutException:
            logger.error("Таймаут при подключении к серверу.")
            await update.message.reply_text(
                "❌ Сервер не отвечает (таймаут). Попробуйте позже.",
                parse_mode="HTML"
            )
        except httpx.RequestError as e:
            logger.error(f"Ошибка при подключении к серверу: {e}")
            await update.message.reply_text(
                "❌ Ошибка при подключении к серверу. Попробуйте позже.",
                parse_mode="HTML"
            )
        return ConversationHandler.END

# Асинхронный обработчик входящих сообщений
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_message = update.message.text

    timeout = httpx.Timeout(120.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            response = await client.get(f"{API_URL}/check_dialog", params={"user_id": user_id})
            response.raise_for_status()
            dialog_status = response.json().get("status", "not_found")
        except httpx.TimeoutException:
            logger.error("Таймаут при проверке диалога.")
            await update.message.reply_text(
                "❌ Сервер не отвечает. Попробуйте позже.",
                parse_mode="HTML"
            )
            return ConversationHandler.END
        except httpx.RequestError as e:
            logger.error(f"Ошибка запроса: {e}")
            await update.message.reply_text(
                "❌ Ошибка при обработке запроса. Попробуйте позже.",
                parse_mode="HTML"
            )
            return ConversationHandler.END

    if dialog_status in ["not_found", "finished"]:
        await update.message.reply_text(
            "Вы ещё не начинали диалог. Запускаю новый...",
            parse_mode="HTML"
        )
        return await start_dialog(update, context)

    msg = await update.message.reply_text(
        "⏳ Генерирую ответ...",
        parse_mode="HTML"
    )

    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            response = await client.post(f"{API_URL}/chat", json={"user_id": user_id, "message": user_message})
            response.raise_for_status()
            bot_reply = response.json().get("response", "Ошибка обработки ответа.")
            formatted_reply = convert_markdown_to_html(bot_reply)

            await msg.edit_text(
                formatted_reply,
                reply_markup=get_inline_keyboard(),
                parse_mode="HTML"
            )
            return TYPING_REPLY
        except httpx.TimeoutException:
            logger.error("Таймаут при генерации ответа от сервера.")
            await msg.edit_text(
                "❌ Время ожидания ответа вышло. Попробуйте позже.",
                parse_mode="HTML"
            )
        except httpx.RequestError as e:
            logger.error(f"Ошибка запроса: {e}")
            await msg.edit_text(
                "❌ Ошибка при обработке запроса. Попробуйте позже.",
                parse_mode="HTML"
            )
        return ConversationHandler.END

# Асинхронный обработчик завершения диалога
async def end_dialog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    timeout = httpx.Timeout(120.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            response = await client.post(f"{API_URL}/end_dialog", params={"user_id": user_id})
            summary = response.json().get("summary", "Ошибка при генерации сводки.")
        except httpx.TimeoutException:
            logger.error("Таймаут при завершении диалога.")
            summary = "Ошибка: превышено время ожидания."
        except httpx.RequestError as e:
            logger.error(f"Ошибка завершения диалога: {e}")
            summary = "Ошибка при обработке запроса."

    formatted_summary = convert_markdown_to_html(summary)

    await query.edit_message_text(
        f"✅ Диалог завершён!\n\n📌 <b>Сводка:</b>\n{formatted_summary}\n\nГотовы начать новую диагностику?",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Решить новую проблему", callback_data="start_dialog")]]),
        parse_mode="HTML"
    )
    return CHOOSING

# Функция main для запуска бота
def main():
    token = os.getenv("TELEGRAM_API_TOKEN")
    application = ApplicationBuilder().token(token).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CHOOSING: [CallbackQueryHandler(start_dialog, pattern="^start_dialog$")],
            TYPING_REPLY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message),
                CallbackQueryHandler(end_dialog, pattern="^end_dialog$"),
            ],
        },
        fallbacks=[CommandHandler("start", start)],
    )

    application.add_handler(conv_handler)
    application.run_polling()

if __name__ == "__main__":
    main()


