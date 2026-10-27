
import logging
import os
import threading
from flask import Flask
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

BOT_TOKEN = os.environ["BOT_TOKEN"]
APK_URL = "https://drive.google.com/file/d/1tpQrjsEFlB_NQ1TbH12byTXZC65I_kqe/view?usp=drivesdk"
CHANNEL_URL = "https://t.me/poliwhis"
ADMIN_CHAT_ID = 1710023187

logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)

web = Flask(__name__)

@web.route("/")
def health():
    return "PoliWhiz Trial bot is running", 200

def run_web():
    port = int(os.environ.get("PORT", "10000"))
    web.run(host="0.0.0.0", port=port, use_reloader=False)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! 👋 Это PoliWhiz-1 Trial.\n\n"
        "Приложение помогает распознавать речь и переводить текст "
        "на Android-устройстве.\n\n"
        "В пробной версии распознаётся только первая минута аудио. "
        "Остальные функции доступны для тестирования.\n\n"
        "Команды:\n"
        "/download — скачать APK\n"
        "/help — инструкция\n"
        "/feedback — оставить отзыв\n\n"
        f"Наш канал: {CHANNEL_URL}"
    )

async def download(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    admin_message = (
        "📥 Запрос на скачивание PoliWhiz Trial\n\n"
        f"От: {user.full_name}\n"
        f"Telegram ID: {user.id}\n"
        f"Username: @{user.username if user.username else 'не указан'}"
    )

    try:
        await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=admin_message,
        )
        logging.info(
            "Уведомление о скачивании отправлено: user_id=%s",
            user.id,
        )
    except Exception:
        logging.exception("Не удалось отправить уведомление о скачивании")

    await update.message.reply_text(
        "📥 Скачать PoliWhiz-1 Trial:\n"
        f"{APK_URL}\n\n"
        "После скачивания открой APK. Если Android попросит разрешение "
        "на установку из этого источника, разреши его и повтори установку."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📱 Как установить PoliWhiz-1 Trial:\n\n"
        "1. Нажми /download и скачай APK.\n"
        "2. Открой скачанный файл на Android.\n"
        "3. Если появится предупреждение, разреши установку "
        "из используемого приложения и повтори попытку.\n"
        "4. Запусти PoliWhiz после установки.\n\n"
        "Пробная версия распознаёт только первую минуту аудио. "
        "Остальные функции доступны для тестирования.\n\n"
        "Чтобы отправить отзыв, нажми /feedback."
    )

async def feedback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["waiting_feedback"] = True
    await update.message.reply_text(
        "💬 Напиши отзыв следующим сообщением. "
        "Пожалуйста, не включай в него пароли, токены или другие секретные данные."
    )

async def receive_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("waiting_feedback"):
        text = update.message.text or ""
        user = update.effective_user

        logging.info(
            "Feedback from user_id=%s username=%s: %s",
            user.id,
            user.username,
            text,
        )

        context.user_data["waiting_feedback"] = False

        admin_message = (
            "📩 Новый отзыв PoliWhiz Trial\n\n"
            f"От: {user.full_name}\n"
            f"Telegram ID: {user.id}\n"
            f"Username: @{user.username if user.username else 'не указан'}\n\n"
            f"Отзыв:\n{text}"
        )

        try:
            await context.bot.send_message(
                chat_id=ADMIN_CHAT_ID,
                text=admin_message,
            )
            logging.info("Отзыв успешно отправлен администратору")
        except Exception:
            logging.exception("Не удалось отправить отзыв администратору")

        await update.message.reply_text(
            "Спасибо за отзыв! 🙏 Он принят. Твой отзыв поможет улучшить PoliWhiz."
        )

def main():
    threading.Thread(target=run_web, daemon=True).start()

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("download", download))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("feedback", feedback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, receive_message))

    app.run_polling()

if __name__ == "__main__":
    main()
