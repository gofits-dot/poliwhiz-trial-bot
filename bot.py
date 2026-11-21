import asyncio
import logging
import os
import hashlib
import hmac
import time
from urllib.parse import urlencode
import threading
import requests
from datetime import datetime
from flask import Flask, redirect
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN") or os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN or BOT_TOKEN must be configured")

APK_URL = "https://drive.google.com/file/d/1SHi6ckfkMSlqD0IUq_Yt4i71BAqyiXZm/view?usp=drivesdk"
CHANNEL_URL = "https://t.me/poliwhis"
CHANNEL_ID = "@poliwhis"
ADMIN_CHAT_ID = 1710023187
DOWNLOAD_PAGE_URL = "https://poliwhiz.com/get-apk"

logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)

web = Flask(__name__)


def subscription_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Подписаться на канал", url=CHANNEL_URL)],
        [InlineKeyboardButton("Проверить подписку", callback_data="check_subscription")],
    ])


def send_email_notification():
    api_key = os.environ.get("RESEND_API_KEY")

    if not api_key:
        logging.error("RESEND_API_KEY is not configured")
        return

    payload = {
        "from": "PoliWhiz <onboarding@resend.dev>",
        "to": ["gofits@gmail.com"],
        "subject": "PoliWhiz Trial — переход к скачиванию",
        "text": (
            "Кто-то перешёл по ссылке для скачивания PoliWhiz Trial.\n"
            "Время события: " + datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        ),
    }

    try:
        response = requests.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=10,
        )
        response.raise_for_status()
        logging.info("Download email notification sent successfully")

    except Exception:
        logging.exception("Failed to send download email notification")


telegram_app = None
telegram_loop = None


async def setup_telegram(application):
    global telegram_app, telegram_loop
    telegram_app = application
    telegram_loop = asyncio.get_running_loop()
    logging.info("Telegram event loop is ready for download notifications")


@web.route("/")
def health():
    return "PoliWhiz Trial bot is running", 200


@web.route("/get-apk")
def get_apk():
    logging.info("APK link clicked")

    try:
        if telegram_app is None or telegram_loop is None:
            raise RuntimeError("Telegram bot is not ready")

        future = asyncio.run_coroutine_threadsafe(
            telegram_app.bot.send_message(
                chat_id=ADMIN_CHAT_ID,
                text=(
                    "📥 Нажатие ссылки PoliWhiz Trial!\n\n"
                    "Пользователь перешёл к скачиванию APK.\n"
                    "Время события: "
                    + datetime.now().strftime("%d.%m.%Y %H:%M:%S")
                ),
            ),
            telegram_loop,
        )

        future.result(timeout=10)
        logging.info("Download click notification sent to administrator")

    except Exception:
        logging.exception("Failed to send download click notification")

    send_email_notification()
    return redirect(APK_URL, code=302)


def run_web():
    port = int(os.environ.get("PORT", "10000"))
    web.run(host="0.0.0.0", port=port, use_reloader=False)


async def is_channel_member(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
    member = await context.bot.get_chat_member(
        chat_id=CHANNEL_ID,
        user_id=user_id,
    )

    if member.status in ("creator", "administrator", "member"):
        return True

    return member.status == "restricted" and bool(getattr(member, "is_member", False))


async def send_subscription_prompt(message):
    await message.reply_text(
        "Чтобы скачать PoliWhiz-1 Trial, подпишись, пожалуйста, на наш канал "
        "@poliwhis, а затем нажми «Проверить подписку».",
        reply_markup=subscription_keyboard(),
    )


async def send_download_link(target, context: ContextTypes.DEFAULT_TYPE, user):
    secret = os.environ.get("DOWNLOAD_SECRET")
    if not secret:
        logging.error("DOWNLOAD_SECRET is not configured")
        await target.reply_text(
            "Сервис выдачи ссылки временно недоступен. Попробуй позже."
        )
        return

    expires = int(time.time()) + 300
    payload = f"{user.id}:{expires}"
    signature = hmac.new(
        secret.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    query = urlencode({
        "user_id": user.id,
        "expires": expires,
        "signature": signature,
    })
    download_url = f"{DOWNLOAD_PAGE_URL}?{query}"

    admin_message = (
        "📥 Запрос на скачивание PoliWhiz Trial\n\n"
        f"От: {user.full_name}\n"
        f"Telegram ID: {user.id}\n"
        f"Username: @{user.username if user.username else 'не указан'}\n"
        "Подписка на @poliwhis подтверждена."
    )

    try:
        await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=admin_message,
        )
        logging.info("Download notification sent: user_id=%s", user.id)
    except Exception:
        logging.exception("Не удалось отправить уведомление о скачивании")

    await target.reply_text(
        "✅ Подписка подтверждена!\n\n"
        "📥 Скачать PoliWhiz-1 Trial:\n"
        f"{download_url}\n\n"
        "После скачивания открой APK. Если Android попросит разрешение "
        "на установку из этого источника, разреши его и повтори установку."
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! 👋 Это PoliWhiz-1 Trial.\n\n"
        "Приложение помогает распознавать речь и переводить текст "
        "на Android-устройстве.\n\n"
        "В пробной версии распознаётся только первая минута аудио. "
        "Остальные функции доступны для тестирования.\n\n"
        "Для скачивания необходимо подписаться на наш канал @poliwhis.\n\n"
        "Команды:\n"
        "/download — скачать APK\n"
        "/help — инструкция\n"
        "/feedback — оставить отзыв",
        reply_markup=subscription_keyboard(),
    )


async def download(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    try:
        subscribed = await is_channel_member(context, user.id)
    except Exception:
        logging.exception("Не удалось проверить подписку user_id=%s", user.id)
        await update.message.reply_text(
            "Сейчас не удалось проверить подписку. Попробуй ещё раз чуть позже."
        )
        return

    if not subscribed:
        await send_subscription_prompt(update.message)
        return

    await send_download_link(update.message, context, user)


async def check_subscription_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query
    await query.answer()
    user = query.from_user

    try:
        subscribed = await is_channel_member(context, user.id)
    except Exception:
        logging.exception("Не удалось проверить подписку user_id=%s", user.id)
        await query.message.reply_text(
            "Не получилось проверить подписку. Попробуй ещё раз немного позже."
        )
        return

    if not subscribed:
        await query.message.reply_text(
            "Пока не вижу подписку на канал @poliwhis. "
            "Подпишись и нажми «Проверить подписку» ещё раз.",
            reply_markup=subscription_keyboard(),
        )
        return

    await send_download_link(query.message, context, user)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📱 Как установить PoliWhiz-1 Trial:\n\n"
        "1. Подпишись на канал @poliwhis.\n"
        "2. Нажми /download и дождись проверки подписки.\n"
        "3. Скачай APK и открой его на Android.\n"
        "4. Если появится предупреждение, разреши установку "
        "из используемого приложения и повтори попытку.\n"
        "5. Запусти PoliWhiz после установки.\n\n"
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


async def post_to_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if user.id != ADMIN_CHAT_ID:
        await update.message.reply_text("У вас нет доступа к этой команде.")
        return

    post_text = update.message.text.partition(" ")[2].strip()

    if not post_text:
        await update.message.reply_text(
            "Использование:\n/post Текст публикации"
        )
        return

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Website", url="https://poliwhiz.com"),
        ],
        [
            InlineKeyboardButton(
                "Audio Tools",
                url="https://poliwhiz.com/splitter"
            ),
        ],
        [
            InlineKeyboardButton(
                "PoliWhiz Trial",
                url="https://t.me/PoliWhizBot"
            ),
        ],
    ])

    await context.bot.send_message(
        chat_id=CHANNEL_ID,
        text=post_text,
        reply_markup=keyboard,
    )

    await update.message.reply_text("Публикация успешно отправлена в канал!")


def main():
    threading.Thread(target=run_web, daemon=True).start()

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(setup_telegram)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("download", download))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("feedback", feedback))
    app.add_handler(CommandHandler("post", post_to_channel))
    app.add_handler(CallbackQueryHandler(
        check_subscription_callback,
        pattern="^check_subscription$",
    ))
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, receive_message)
    )

    app.run_polling()


if __name__ == "__main__":
    main()
