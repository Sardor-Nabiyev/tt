"""Oddiy JSON fayl ombori. Har bir Telegram foydalanuvchisining ma'lumotlari alohida saqlanadi."""
import json
import logging
import os
from copy import deepcopy

DEFAULT_USER = {
    "authorized": False,
    "next_id": 1,
    "transactions": [],  # haqiqiy daromad/chiqimlar
    "debts": [],         # kreditlar va qarzlar
    "planned": [],       # kutilayotgan (rejalashtirilgan) daromad/chiqimlar
    "settings": {"remind": True},
}


class JsonDB:
    def __init__(self, path):
        self.path = path
        self.data = self._load()

    def _load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            data = {}
        except json.JSONDecodeError:
            broken = self.path + ".corrupt"
            os.replace(self.path, broken)
            logging.error("database fayli buzilgan, %s ga ko'chirildi", broken)
            data = {}
        data.setdefault("users", {})
        return data

    def save(self):
        folder = os.path.dirname(os.path.abspath(self.path))
        os.makedirs(folder, exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self.path)

    def is_authorized(self, uid):
        return self.data["users"].get(str(uid), {}).get("authorized", False)

    def user(self, uid):
        users = self.data["users"]
        u = users.setdefault(str(uid), deepcopy(DEFAULT_USER))
        for key, value in DEFAULT_USER.items():
            u.setdefault(key, deepcopy(value))
        return u

    def users(self):
        return [(int(uid), self.user(uid)) for uid in list(self.data["users"])]
