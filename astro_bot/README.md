# Astro Bot

Функциональный Telegram‑бот на Python (python-telegram-bot + skyfield) для ежедневных персональных сообщений на основе астрологических транзитов, с реферальной программой и подпиской через Telegram Payments.

## Быстрый старт

1. Создай `.env` из примера и укажи токены:
```
cp .env.example .env
# отредактируй значения
```

2. Активируй окружение и установи зависимости:
```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

3. Запуск:
```
python bot.py
```

## Возможности
- /start — ввод имени, даты/места/времени рождения и желаемого времени рассылки
- Хранение профилей в SQLite (`data/bot.db`)
- Ежедневная рассылка по JobQueue в выбранное время
- Реальные транзиты с Skyfield и простая интерпретация аспектов
- Меню /menu — смена времени, реферальная ссылка/статистика, подписка
- /broadcast (для ADMIN_USER_ID) — массовая рассылка
- Подписка через Telegram Payments (`/subscribe`)

## Примечания
- Файлы с цитатами: `quotes/secret.txt`, `quotes/happy_pocket.txt` — по одной цитате в строке.
- Часовой пояс задаётся переменной окружения `TIMEZONE` (по умолчанию Europe/Moscow).