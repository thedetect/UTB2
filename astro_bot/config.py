import os
from dataclasses import dataclass
from datetime import timedelta


@dataclass(frozen=True)
class Config:
    telegram_bot_token: str
    payment_provider_token: str
    admin_user_id: int
    database_path: str
    timezone: str
    currency: str
    price_minor_units: int
    subscription_duration: timedelta
    # Google Sheets
    gsheet_spreadsheet_id: str
    gsheet_credentials_path: str | None
    gsheet_credentials_json: str | None


def load_config() -> Config:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    provider_token = os.environ.get("PAYMENT_PROVIDER_TOKEN", "")
    admin_user_id = int(os.environ.get("ADMIN_USER_ID", "0") or 0)
    database_path = os.environ.get(
        "DATABASE_PATH", "/workspace/astro_bot/data/bot.db"
    )
    timezone = os.environ.get("TIMEZONE", "Europe/Moscow")

    currency = os.environ.get("PAY_CURRENCY", "RUB")
    price_minor_units = int(os.environ.get("PAY_PRICE_MINOR", "29900"))
    # Default: 30 days
    subscription_duration_days = int(os.environ.get("SUB_DURATION_DAYS", "30"))

    # Google Sheets
    gsheet_spreadsheet_id = os.environ.get("GSHEET_SPREADSHEET_ID", "")
    gsheet_credentials_path = os.environ.get("GSHEET_CREDENTIALS_PATH")
    gsheet_credentials_json = os.environ.get("GSHEET_CREDENTIALS_JSON")

    return Config(
        telegram_bot_token=token,
        payment_provider_token=provider_token,
        admin_user_id=admin_user_id,
        database_path=database_path,
        timezone=timezone,
        currency=currency,
        price_minor_units=price_minor_units,
        subscription_duration=timedelta(days=subscription_duration_days),
        gsheet_spreadsheet_id=gsheet_spreadsheet_id,
        gsheet_credentials_path=gsheet_credentials_path,
        gsheet_credentials_json=gsheet_credentials_json,
    )