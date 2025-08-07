import aiosqlite
from typing import Optional, List, Tuple, Dict, Any
from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass
class User:
    user_id: int
    name: Optional[str]
    birth_date: Optional[str]  # DD.MM.YYYY
    birth_place: Optional[str]
    birth_time: Optional[str]  # HH:MM
    daily_time: Optional[str]  # HH:MM local
    timezone: Optional[str]
    created_at: str
    updated_at: str
    referrer_id: Optional[int]
    referral_code: Optional[str]
    points: int
    is_subscribed: int  # 0/1
    subscription_until: Optional[str]
    ever_paid: Optional[int] = 0


class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path

    async def init(self) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    name TEXT,
                    birth_date TEXT,
                    birth_place TEXT,
                    birth_time TEXT,
                    daily_time TEXT,
                    timezone TEXT,
                    created_at TEXT,
                    updated_at TEXT,
                    referrer_id INTEGER,
                    referral_code TEXT UNIQUE,
                    points INTEGER DEFAULT 0,
                    is_subscribed INTEGER DEFAULT 0,
                    subscription_until TEXT
                );
                """
            )
            # Миграция: добавляем столбец ever_paid при его отсутствии
            try:
                await db.execute("ALTER TABLE users ADD COLUMN ever_paid INTEGER DEFAULT 0")
            except Exception:
                pass

            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS referrals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    referrer_id INTEGER NOT NULL,
                    referred_user_id INTEGER NOT NULL,
                    created_at TEXT
                );
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    sent_at TEXT NOT NULL,
                    content TEXT
                );
                """
            )
            await db.commit()

    async def upsert_user_basic(self, user_id: int, timezone: str) -> None:
        now = datetime.utcnow().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO users(user_id, timezone, created_at, updated_at, referral_code)
                VALUES(?, ?, ?, ?, COALESCE((SELECT referral_code FROM users WHERE user_id=?), CAST(ABS(RANDOM()) AS TEXT)))
                ON CONFLICT(user_id) DO UPDATE SET updated_at=excluded.updated_at;
                """,
                (user_id, timezone, now, now, user_id),
            )
            await db.commit()

    async def set_user_profile(
        self,
        user_id: int,
        name: str,
        birth_date: str,
        birth_place: str,
        birth_time: str,
        daily_time: str,
    ) -> None:
        now = datetime.utcnow().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                UPDATE users SET name=?, birth_date=?, birth_place=?, birth_time=?, daily_time=?, updated_at=?
                WHERE user_id=?
                """,
                (name, birth_date, birth_place, birth_time, daily_time, now, user_id),
            )
            await db.commit()

    async def get_user(self, user_id: int) -> Optional[User]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM users WHERE user_id=?", (user_id,)) as cur:
                row = await cur.fetchone()
                if not row:
                    return None
                return User(**dict(row))

    async def list_users(self) -> List[User]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM users") as cur:
                rows = await cur.fetchall()
                return [User(**dict(r)) for r in rows]

    async def set_daily_time(self, user_id: int, daily_time: str) -> None:
        now = datetime.utcnow().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE users SET daily_time=?, updated_at=? WHERE user_id=?",
                (daily_time, now, user_id),
            )
            await db.commit()

    async def add_referral(self, referrer_id: int, referred_user_id: int, points: int = 10) -> None:
        now = datetime.utcnow().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO referrals(referrer_id, referred_user_id, created_at) VALUES (?, ?, ?)",
                (referrer_id, referred_user_id, now),
            )
            await db.execute(
                "UPDATE users SET points = COALESCE(points, 0) + ? WHERE user_id=?",
                (points, referrer_id),
            )
            await db.commit()

    async def get_referral_stats(self, user_id: int) -> Tuple[int, int]:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT COUNT(*), COALESCE((SELECT points FROM users WHERE user_id=?), 0) FROM referrals WHERE referrer_id=?",
                (user_id, user_id),
            ) as cur:
                row = await cur.fetchone()
                referred_count = int(row[0]) if row else 0
                points = int(row[1]) if row else 0
                return referred_count, points

    async def count_paid_referrals(self, referrer_id: int) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                """
                SELECT COUNT(*)
                FROM referrals r
                JOIN users u ON u.user_id = r.referred_user_id
                WHERE r.referrer_id = ? AND (COALESCE(u.ever_paid,0)=1 OR COALESCE(u.is_subscribed,0)=1)
                """,
                (referrer_id,),
            ) as cur:
                row = await cur.fetchone()
                return int(row[0]) if row else 0

    async def set_referrer(self, user_id: int, referrer_id: int) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("UPDATE users SET referrer_id=? WHERE user_id=?", (referrer_id, user_id))
            await db.commit()

    async def set_referral_code(self, user_id: int, code: str) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE users SET referral_code=? WHERE user_id=?",
                (code, user_id),
            )
            await db.commit()

    async def get_user_by_code(self, code: str) -> Optional[User]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM users WHERE referral_code=?", (code,)) as cur:
                row = await cur.fetchone()
                return User(**dict(row)) if row else None

    async def set_subscription(self, user_id: int, until: datetime) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE users SET is_subscribed=1, subscription_until=? WHERE user_id=?",
                (until.isoformat(), user_id),
            )
            await db.commit()

    async def mark_ever_paid(self, user_id: int) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("UPDATE users SET ever_paid=1 WHERE user_id=?", (user_id,))
            await db.commit()

    async def clear_subscription(self, user_id: int) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE users SET is_subscribed=0, subscription_until=NULL WHERE user_id=?",
                (user_id,),
            )
            await db.commit()

    async def track_message(self, user_id: int, content: str) -> None:
        now = datetime.utcnow().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO messages(user_id, sent_at, content) VALUES (?, ?, ?)",
                (user_id, now, content),
            )
            await db.commit()