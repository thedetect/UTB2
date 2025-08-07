from datetime import datetime
from telegram import LabeledPrice, Invoice
from telegram.ext import ContextTypes

from config import Config
from database import Database


SUBSCRIPTION_TITLE = "Подписка на Вселенную"
SUBSCRIPTION_DESC = "Полный доступ к ежедневным астросообщениям и бонусам."


async def create_invoice(config: Config) -> dict:
    return {
        "title": SUBSCRIPTION_TITLE,
        "description": SUBSCRIPTION_DESC,
        "payload": "subscription-payload",
        "provider_token": config.payment_provider_token,
        "currency": config.currency,
        "prices": [LabeledPrice("Подписка", config.price_minor_units)],
        "start_parameter": "subscription",
    }


async def handle_successful_payment(config: Config, db: Database, user_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    now = datetime.utcnow()
    until = now + config.subscription_duration
    await db.set_subscription(user_id, until)
    await context.bot.send_message(
        chat_id=user_id,
        text=(
            "Спасибо за оплату! Подписка активирована. "
            f"Действует до: {until.strftime('%d.%m.%Y %H:%M UTC')}"
        ),
    )