#telegram_bot.py

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

API_URL = os.getenv("API_URL")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("bot.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

CHOOSING, TYPING_REPLY = range(2)

WELCOME_MESSAGE = """
<b>🔹 1. Чётко формулируйте проблему</b>  
<pre>❌ «Не работает линия»
✅ «Линия остановилась после резки, был щелчок»</pre>

<b>🔹 2. Отвечайте развёрнуто</b>  
<pre>❌ «Проверили»
✅ «Проводка в норме, окислов нет, разъёмы целы»</pre>

<b>🔹 3. Делитесь наблюдениями</b>  
Шум, запах, свет — даже мелочи могут помочь найти причину
<pre>❌  «Ну просто встал и всё»
✅ «Перед остановкой появился резкий запах гари»</pre>


<b>Чтобы открыть диалог нажмите кнопку</b>
⬇️⬇️⬇️
"""

START_MESSAGE = """
🟢 <b>Диалог открыт.</b>

Подробно опишите проблему 
"""


def convert_markdown_to_html(text: str) -> str:
    text = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"\*(.*?)\*", r"<i>\1</i>", text)
    text = re.sub(r"^### (.*?)$", r"<b><u>\1</u></b>", text, flags=re.MULTILINE)
    text = re.sub(r"\n- ", r"\n• ", text)
    return text


def get_inline_keyboard():
    keyboard = [[InlineKeyboardButton("✅ Проблема решена", callback_data="end_dialog")]]
    return InlineKeyboardMarkup(keyboard)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("🔧 Разобраться с проблемой", callback_data="start_dialog")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        WELCOME_MESSAGE,
        reply_markup=reply_markup,
        parse_mode="HTML"
    )
    return CHOOSING


async def start_dialog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    timeout = httpx.Timeout(120.0)

    if update.callback_query:
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id

        try:
            await context.bot.edit_message_reply_markup(
                chat_id=query.message.chat_id,
                message_id=query.message.message_id,
                reply_markup=None
            )
        except:
            pass

        async with httpx.AsyncClient(timeout=timeout) as client:
            # 💥 Завершаем старый диалог без генерации сводки
            await client.post(f"{API_URL}/force_end_dialog", params={"user_id": user_id})
            # 🆕 Стартуем новый диалог
            await client.post(f"{API_URL}/start_dialog", params={"user_id": user_id})

        #await query.message.reply_text("╔═══════════════════╗")
        await query.message.reply_text(START_MESSAGE, parse_mode="HTML")
        return TYPING_REPLY

    else:
        user_id = update.effective_user.id
        await update.message.reply_text(START_MESSAGE, parse_mode="HTML")

        async with httpx.AsyncClient(timeout=timeout) as client:
            await client.post(f"{API_URL}/force_end_dialog", params={"user_id": user_id})
            await client.post(f"{API_URL}/start_dialog", params={"user_id": user_id})

        return TYPING_REPLY


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_message = update.message.text

    timeout = httpx.Timeout(120.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.get(f"{API_URL}/check_dialog", params={"user_id": user_id})
        dialog_data = response.json()

    if not dialog_data.get("active"):
        await update.message.reply_text("Вы ещё не начинали диалог. Запускаю новый...", parse_mode="HTML")
        return await start_dialog(update, context)

    # 🧹 Удаление предыдущих кнопок, если они есть
    if "last_bot_message_id" in context.user_data:
        try:
            await context.bot.edit_message_reply_markup(
                chat_id=update.effective_chat.id,
                message_id=context.user_data["last_bot_message_id"],
                reply_markup=None
            )
        except:
            pass  # если сообщение не найдено или уже изменено — игнорируем

    msg = await update.message.reply_text(
    "⏳ Генерирую ответ...",
    parse_mode="HTML"
    )

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(f"{API_URL}/chat", json={"user_id": user_id, "message": user_message})
        response.raise_for_status()
        raw_reply = response.json().get("response")

    # Безопасная обработка даже если response = None или пустая строка
    if not isinstance(raw_reply, str) or not raw_reply.strip():
        logging.warning(f"⚠️ GPT вернул пустую строку или None для user_id={user_id}")
        safe_text = "🤖 Пока ничего не могу сказать. Попробуйте уточнить вопрос."  # невидимый символ U+200E
    else:
        safe_text = convert_markdown_to_html(raw_reply.strip())

    await msg.edit_text(
        safe_text,
        reply_markup=get_inline_keyboard(),
        parse_mode="HTML"
    )
    # 💾 Сохраняем ID последнего сообщения с кнопкой
    context.user_data["last_bot_message_id"] = msg.message_id

    return TYPING_REPLY

async def end_dialog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    timeout = httpx.Timeout(120.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(f"{API_URL}/end_dialog", params={"user_id": user_id})
        summary = response.json().get("summary", "Ошибка при генерации сводки.")

    formatted_summary = convert_markdown_to_html(summary)

    # 🧹 Удаляем кнопки у последнего сообщения от бота, если оно есть
    if "last_bot_message_id" in context.user_data:
        try:
            await context.bot.edit_message_reply_markup(
                chat_id=query.message.chat_id,
                message_id=context.user_data["last_bot_message_id"],
                reply_markup=None
            )
        except:
            pass  # если сообщение уже изменено/удалено
    
    # ➕ Добавляем рамку завершения
    # await query.message.reply_text("╚═══════════════════╝")

    # 📩 Отправляем новое сообщение со сводкой
    await query.message.reply_text(
        f"🏁<b>Диалог завершён!</b>\n\n📌 <b>Сводка:</b>\n{formatted_summary}\n\n<b>Чтобы открыть диалог нажмите кнопку</b>\n⬇️⬇️⬇️",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("🔧 Разобраться с проблемой", callback_data="start_dialog")]]
        ),
        parse_mode="HTML"
    )

    return CHOOSING


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
