from typing import Optional, Tuple
from urllib.parse import urlencode

from database import Database


def build_ref_link(bot_username: str, code: str) -> str:
    return f"https://t.me/{bot_username}?start={code}"


async def ensure_user_code(db: Database, user_id: int) -> str:
    user = await db.get_user(user_id)
    if user and user.referral_code:
        return user.referral_code
    # Stable deterministic code based on user_id
    code = f"u{user_id}"
    await db.set_referral_code(user_id, code)
    return code


async def process_start_payload(db: Database, current_user_id: int, payload: Optional[str]) -> Optional[int]:
    if not payload:
        return None
    ref_user = await db.get_user_by_code(payload)
    if ref_user and ref_user.user_id != current_user_id:
        await db.set_referrer(current_user_id, ref_user.user_id)
        await db.add_referral(ref_user.user_id, current_user_id)
        return ref_user.user_id
    return None


async def referral_stats(db: Database, user_id: int) -> Tuple[int, int]:
    return await db.get_referral_stats(user_id)