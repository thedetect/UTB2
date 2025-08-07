import asyncio
import logging
import os
from datetime import datetime, time
from typing import Optional
from dateutil import tz

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    CallbackQueryHandler,
    PreCheckoutQueryHandler,
    ContextTypes,
    filters,
)

from config import load_config
from database import Database
from astrology import AstrologyEngine, load_quotes
from referral import ensure_user_code, process_start_payload, build_ref_link, referral_stats
from payments import create_invoice, handle_successful_payment
from gsheets import GoogleSheetClient, SheetConfig

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Conversation states
(ASK_NAME, ASK_BDATE, ASK_BPLACE, ASK_BTIME, ASK_SENDTIME, CONFIRM) = range(6)


def parse_time_str(value: str) -> Optional[time]:
    try:
        hh, mm = map(int, value.strip().split(":"))
        if 0 <= hh < 24 and 0 <= mm < 60:
            return time(hh, mm)
    except Exception:
        pass
    return None


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    config = context.bot_data["config"]
    db: Database = context.bot_data["db"]

    payload = None
    if context.args:
        # deep-link payload
        payload = context.args[0]
    await db.upsert_user_basic(update.effective_user.id, config.timezone)
    await process_start_payload(db, update.effective_user.id, payload)

    await update.message.reply_text(
        "Добро пожаловать во Вселенную! ✨\n\nЯ помогу рассчитать твой персональный астропрогноз.\nДавай начнем с твоего имени.")
    return ASK_NAME


async def ask_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["name"] = update.message.text.strip().title()[:64]
    await update.message.reply_text("Укажи дату рождения (пример: 27.11.1997):")
    return ASK_BDATE


async def ask_bdate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    try:
        datetime.strptime(text, "%d.%m.%Y")
    except ValueError:
        await update.message.reply_text("Неверный формат. Введи дату как ДД.ММ.ГГГГ")
        return ASK_BDATE
    context.user_data["bdate"] = text
    await update.message.reply_text("Место рождения (город, страна):")
    return ASK_BPLACE


async def ask_bplace(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["bplace"] = update.message.text.strip()[:128]
    await update.message.reply_text("Точное время рождения (например, 18:25):")
    return ASK_BTIME


async def ask_btime(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if parse_time_str(text) is None:
        await update.message.reply_text("Формат времени HH:MM, напиши ещё раз.")
        return ASK_BTIME
    context.user_data["btime"] = text
    await update.message.reply_text("Во сколько присылать сообщение каждый день? (например, 10:05):")
    return ASK_SENDTIME


async def ask_sendtime(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    t = parse_time_str(text)
    if t is None:
        await update.message.reply_text("Формат времени HH:MM, напиши ещё раз.")
        return ASK_SENDTIME

    context.user_data["send_time"] = text
    db: Database = context.bot_data["db"]

    await db.set_user_profile(
        user_id=update.effective_user.id,
        name=context.user_data["name"],
        birth_date=context.user_data["bdate"],
        birth_place=context.user_data["bplace"],
        birth_time=context.user_data["btime"],
        daily_time=text,
    )

    summary = (
        "Спасибо! Вот твои данные:\n\n"
        f"Имя: {context.user_data['name']}\n"
        f"Дата рождения: {context.user_data['bdate']}\n"
        f"Место рождения: {context.user_data['bplace']}\n"
        f"Время рождения: {context.user_data['btime']}\n"
        f"Время рассылки: {text}"
    )

    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("Поговорить со Вселенной", callback_data="talk")]]
    )
    await update.message.reply_text(summary)
    await update.message.reply_text("Готов рассчитать твой первый астропрогноз!", reply_markup=keyboard)
    return CONFIRM


async def confirm_first(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    db: Database = context.bot_data["db"]
    engine: AstrologyEngine = context.bot_data["engine"]
    quotes = context.bot_data["quotes"]
    user = await db.get_user(user_id)
    if not user:
        await query.edit_message_text("Профиль не найден. Попробуй /start")
        return ConversationHandler.END

    natal = engine.natal_chart(user.birth_date, user.birth_time, user.timezone or "Europe/Moscow")
    transit = engine.transit_chart(user.timezone or "Europe/Moscow")
    aspects = engine.compute_aspects(natal, transit)
    text = engine.render_daily_message(user.name or "друг", aspects, quotes)
    await context.bot.send_message(chat_id=user_id, text=text)
    await db.track_message(user_id, text)

    # Google Sheet: добавим/обновим строку при завершении регистрации
    sheet: GoogleSheetClient | None = context.bot_data.get("gsheet")
    if sheet:
        me = await context.bot.get_me()
        from referral import ensure_user_code, build_ref_link
        code = await ensure_user_code(db, user_id)
        ref_link = build_ref_link(me.username, code)
        count, _ = await db.get_referral_stats(user_id)
        paid_count = await db.count_paid_referrals(user_id)
        await asyncio.get_running_loop().run_in_executor(
            None,
            lambda: sheet.upsert_user(
                user_id=user_id,
                name=user.name or "",
                birth_date=user.birth_date or "",
                birth_time=user.birth_time or "",
                birth_place=user.birth_place or "",
                created_at_iso=user.created_at,
                is_paid=bool(user.is_subscribed),
                amount=None,
                paid_at=user.subscription_until,
                ref_link=ref_link,
                referrals_count=count,
                paid_referrals_count=paid_count,
                given_days=0,
                ever_paid=bool(user.ever_paid),
            ),
        )

    # schedule daily
    await schedule_user_job(context, user_id, user.daily_time or "10:00")

    await query.edit_message_text("Первый прогноз отправлен. Я буду писать каждый день в назначенное время.")
    return ConversationHandler.END


async def schedule_user_job(context: ContextTypes.DEFAULT_TYPE, user_id: int, time_str: str) -> None:
    job_name = f"daily_{user_id}"
    # Remove previous job
    for job in context.job_queue.get_jobs_by_name(job_name):
        job.schedule_removal()

    hh, mm = map(int, time_str.split(":"))
    context.job_queue.run_daily(
        callback=send_daily_message,
        time=time(hh, mm),
        name=job_name,
        data={"user_id": user_id},
    )


async def send_daily_message(context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = context.job.data["user_id"]
    db: Database = context.bot_data["db"]
    engine: AstrologyEngine = context.bot_data["engine"]
    quotes = context.bot_data["quotes"]

    user = await db.get_user(user_id)
    if not user:
        return
    # Gate by subscription: allow if subscribed or first message exists? Here: require subscription
    if not user.is_subscribed:
        await context.bot.send_message(chat_id=user_id, text="Чтобы получать ежедневные сообщения, оформи подписку командой /subscribe.")
        return

    natal = engine.natal_chart(user.birth_date, user.birth_time, user.timezone or "Europe/Moscow")
    transit = engine.transit_chart(user.timezone or "Europe/Moscow")
    aspects = engine.compute_aspects(natal, transit)
    text = engine.render_daily_message(user.name or "друг", aspects, quotes)
    await context.bot.send_message(chat_id=user_id, text=text)
    await db.track_message(user_id, text)


async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        [InlineKeyboardButton("Изменить время рассылки", callback_data="edit_time")],
        [InlineKeyboardButton("Мои рефералы", callback_data="ref_status")],
        [InlineKeyboardButton("Получить реферальную ссылку", callback_data="ref_link")],
        [InlineKeyboardButton("Подписка", callback_data="sub")],
    ]
    await update.message.reply_text("Меню:", reply_markup=InlineKeyboardMarkup(keyboard))


async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    db: Database = context.bot_data["db"]

    if query.data == "edit_time":
        await query.edit_message_text("Введи новое время в формате HH:MM")
        context.user_data["await_time"] = True
    elif query.data == "ref_status":
        count, points = await referral_stats(db, query.from_user.id)
        await query.edit_message_text(f"Приглашено: {count}\nБаллы: {points}")
    elif query.data == "ref_link":
        me = await context.bot.get_me()
        code = await ensure_user_code(db, query.from_user.id)
        link = build_ref_link(me.username, code)
        await query.edit_message_text(f"Твоя ссылка:\n{link}")
    elif query.data == "sub":
        config = context.bot_data["config"]
        if not config.payment_provider_token:
            await query.edit_message_text("Платёжный провайдер не настроен.")
            return
        invoice = await create_invoice(config)
        await context.bot.send_invoice(chat_id=query.message.chat_id, **invoice)
        await query.edit_message_text("Отправил счёт на оплату подписки.")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if context.user_data.get("await_time"):
        t = parse_time_str(update.message.text.strip())
        if t is None:
            await update.message.reply_text("Формат времени HH:MM, попробуй снова")
            return
        db: Database = context.bot_data["db"]
        await db.set_daily_time(update.effective_user.id, update.message.text.strip())
        await schedule_user_job(context, update.effective_user.id, update.message.text.strip())
        await update.message.reply_text("Время обновлено! Буду писать в указанное время.")
        context.user_data["await_time"] = False


async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    config = context.bot_data["config"]
    if update.effective_user.id != config.admin_user_id:
        await update.message.reply_text("Команда только для администратора")
        return
    text = " ".join(context.args) if context.args else ""
    if not text:
        await update.message.reply_text("Использование: /broadcast <текст>")
        return
    db: Database = context.bot_data["db"]
    users = await db.list_users()
    sent = 0
    for u in users:
        try:
            await context.bot.send_message(chat_id=u.user_id, text=text)
            sent += 1
        except Exception as e:
            logger.warning("Broadcast to %s failed: %s", u.user_id, e)
    await update.message.reply_text(f"Отправлено: {sent}")


async def subscribe_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    config = context.bot_data["config"]
    if not config.payment_provider_token:
        await update.message.reply_text("Платёжный провайдер не настроен.")
        return
    invoice = await create_invoice(config)
    await update.message.reply_invoice(**invoice)


async def successful_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    config = context.bot_data["config"]
    db: Database = context.bot_data["db"]
    user_id = update.message.from_user.id
    await handle_successful_payment(config, db, user_id, context)
    await db.mark_ever_paid(user_id)

    # Обновим строку в Google Sheet
    sheet: GoogleSheetClient | None = context.bot_data.get("gsheet")
    if sheet:
        user = await db.get_user(user_id)
        me = await context.bot.get_me()
        code = await ensure_user_code(db, user_id)
        ref_link = build_ref_link(me.username, code)
        count, _ = await db.get_referral_stats(user_id)
        paid_count = await db.count_paid_referrals(user_id)
        await asyncio.get_running_loop().run_in_executor(
            None,
            lambda: sheet.upsert_user(
                user_id=user_id,
                name=user.name or "",
                birth_date=user.birth_date or "",
                birth_time=user.birth_time or "",
                birth_place=user.birth_place or "",
                created_at_iso=user.created_at,
                is_paid=bool(user.is_subscribed),
                amount=(config.price_minor_units / 100.0),
                paid_at=user.subscription_until,
                ref_link=ref_link,
                referrals_count=count,
                paid_referrals_count=paid_count,
                given_days=int(config.subscription_duration.days),
                ever_paid=True,
            ),
        )


async def precheckout_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.pre_checkout_query
    await query.answer(ok=True)


async def post_init(app: Application) -> None:
    # Load config, DB, engines, quotes
    config = load_config()
    app.bot_data["config"] = config

    db = Database(config.database_path)
    await db.init()
    app.bot_data["db"] = db

    engine = AstrologyEngine()
    app.bot_data["engine"] = engine

    quotes = load_quotes(os.path.join(os.path.dirname(__file__), "quotes"))
    app.bot_data["quotes"] = quotes

    # Google Sheets client
    if config.gsheet_spreadsheet_id:
        sheet_cfg = SheetConfig(
            spreadsheet_id=config.gsheet_spreadsheet_id,
            credentials_path=config.gsheet_credentials_path,
            credentials_json=config.gsheet_credentials_json,
        )
        try:
            gsheet = GoogleSheetClient(sheet_cfg)
            gsheet.init()
            app.bot_data["gsheet"] = gsheet
            logger.info("Google Sheets connected")
        except Exception as e:
            logger.warning("Google Sheets init failed: %s", e)

    # Schedule existing users
    users = await db.list_users()
    for u in users:
        if u.daily_time:
            await schedule_user_job(app, u.user_id, u.daily_time)


def build_application() -> Application:
    config = load_config()
    if not config.telegram_bot_token:
        raise RuntimeError("Не задан TELEGRAM_BOT_TOKEN в окружении")

    app = (
        ApplicationBuilder()
        .token(config.telegram_bot_token)
        .post_init(post_init)
        .timezone(tz.gettz(config.timezone))
        .build()
    )

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            ASK_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_name)],
            ASK_BDATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_bdate)],
            ASK_BPLACE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_bplace)],
            ASK_BTIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_btime)],
            ASK_SENDTIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_sendtime)],
            CONFIRM: [CallbackQueryHandler(confirm_first, pattern="^talk$")],
        },
        fallbacks=[],
    )

    app.add_handler(conv)
    app.add_handler(CommandHandler("menu", menu))
    app.add_handler(CallbackQueryHandler(menu_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CommandHandler("subscribe", subscribe_cmd))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_callback))
    app.add_handler(PreCheckoutQueryHandler(precheckout_handler))

    return app


def main():
    app = build_application()
    app.run_polling()


if __name__ == "__main__":
    main()