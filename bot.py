"""Moliya nazorati Telegram boti: kirish nuqtasi, kirish kodi va kundalik eslatmalar."""
import asyncio
import logging
from datetime import datetime, timedelta

from aiogram import BaseMiddleware, Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Message

import finance as fn
from config import ADMIN_CODE, DATA_PATH, REMIND_HOUR, TOKEN, TZ, today
from handlers import main_kb, router
from jsondb import JsonDB


class AuthMiddleware(BaseMiddleware):
    """ADMIN_CODE berilgan bo'lsa, botdan faqat kodni bilganlar foydalana oladi."""

    def __init__(self, db, code):
        self.db = db
        self.code = code

    async def __call__(self, handler, event, data):
        user = getattr(event, "from_user", None)
        if not self.code or user is None or self.db.is_authorized(user.id):
            return await handler(event, data)
        if isinstance(event, Message):
            if (event.text or "").strip() == self.code:
                self.db.user(user.id)["authorized"] = True
                self.db.save()
                await event.answer("✅ Kirish tasdiqlandi. /start bosing.", reply_markup=main_kb())
            else:
                await event.answer("🔒 Bu shaxsiy bot. Kirish kodini yuboring.")
        elif isinstance(event, CallbackQuery):
            await event.answer("🔒 Avval kirish kodini yuboring", show_alert=True)


def reminder_text(user, t):
    events = fn.upcoming(user, t, 3)
    if not events:
        return None
    lines = ["🔔 <b>Eslatma</b>\n"]
    for e in events:
        if e["overdue"]:
            when = "⚠️ muddati o'tgan"
        elif e["date"] == t:
            when = "bugun"
        elif e["date"] == t + timedelta(days=1):
            when = "ertaga"
        else:
            when = fn.fmt_date(e["date"])
        sign = "➕" if e["type"] == fn.INCOME else "➖"
        lines.append(f"{sign} {e['title']} — <b>{fn.fmt_money(e['amount'])}</b> ({when})")
    lines.append("\nBajarilganini 📅 Kutilayotganlar yoki 💳 Kredit va qarzlar bo'limida belgilang.")
    return "\n".join(lines)


async def send_reminders(bot, db):
    t = today()
    for uid, user in db.users():
        if ADMIN_CODE and not user.get("authorized"):
            continue
        if not user["settings"].get("remind", True):
            continue
        text = reminder_text(user, t)
        if not text:
            continue
        try:
            await bot.send_message(uid, text)
        except Exception as e:  # foydalanuvchi botni bloklagan bo'lishi mumkin
            logging.warning("Eslatma yuborilmadi %s: %s", uid, e)


async def reminder_loop(bot, db):
    while True:
        now = datetime.now(TZ)
        target = now.replace(hour=REMIND_HOUR, minute=0, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        await asyncio.sleep((target - now).total_seconds())
        await send_reminders(bot, db)


async def main():
    logging.basicConfig(level=logging.INFO)
    if not TOKEN:
        raise SystemExit("TOKEN o'zgaruvchisi berilmagan")
    db = JsonDB(DATA_PATH)
    bot = Bot(TOKEN, parse_mode=ParseMode.HTML)
    dp = Dispatcher(storage=MemoryStorage(), db=db)
    auth = AuthMiddleware(db, ADMIN_CODE)
    dp.message.outer_middleware(auth)
    dp.callback_query.outer_middleware(auth)
    dp.include_router(router)

    reminders = asyncio.create_task(reminder_loop(bot, db))  # noqa: F841 (havolani saqlash)
    logging.info("Polling started")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
