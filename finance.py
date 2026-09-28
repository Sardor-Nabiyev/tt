"""Moliyaviy hisob-kitoblar: summalar, sanalar, kutilayotgan to'lovlar, prognoz.

Bu modul Telegram'ga bog'liq emas — faqat foydalanuvchi ma'lumotlari (dict) bilan ishlaydi.
"""
import calendar
import math
import re
from datetime import date, timedelta

EXPENSE = "expense"
INCOME = "income"

DEBT_KINDS = {
    "credit": "Bank krediti",
    "i_owe": "Men qarzdorman",
    "owed_to_me": "Menga qarzdor",
}

EXPENSE_CATEGORIES = [
    "Oziq-ovqat", "Transport", "Kommunal", "Uy-joy", "Sog'liq",
    "Kiyim", "Aloqa", "Ko'ngilochar", "Ta'lim", "Boshqa",
]
INCOME_CATEGORIES = ["Oylik", "Biznes", "Qo'shimcha ish", "Sovg'a", "Boshqa"]

DEBT_PAYMENT_CATEGORY = "Kredit/qarz to'lovi"
DEBT_RETURN_CATEGORY = "Qarz qaytdi"


# ---------- Formatlash va parsing ----------

def fmt_money(x):
    return f"{x:,.0f}".replace(",", " ") + " so'm"


def fmt_date(d):
    if isinstance(d, str):
        d = date.fromisoformat(d)
    return d.strftime("%d.%m.%Y")


_MULTIPLIERS = {"k": 1_000, "ming": 1_000, "m": 1_000_000, "mln": 1_000_000, "million": 1_000_000}


def parse_amount(text):
    """'50000', '50 000', '1,200,000', '50k', '1.5mln' -> float. Noto'g'ri bo'lsa None."""
    if not text:
        return None
    s = text.strip().lower().replace(" ", "").replace("so'm", "").replace("som", "")
    m = re.fullmatch(r"([\d.,]+)(k|ming|mln|million|m)?", s)
    if not m:
        return None
    num, suffix = m.groups()
    if suffix:
        num = num.replace(",", ".")
        if num.count(".") > 1:
            return None
    else:
        seps = [c for c in num if c in ".,"]
        if len(seps) > 1:
            num = num.replace(",", "").replace(".", "")
        elif len(seps) == 1:
            whole, frac = re.split(r"[.,]", num)
            num = whole + frac if len(frac) == 3 else f"{whole}.{frac}"
    try:
        value = float(num) * _MULTIPLIERS.get(suffix, 1)
    except ValueError:
        return None
    return value if value > 0 else None


def add_months(d, n, day=None):
    """Sanaga n oy qo'shadi; 31-kun kabi kunlar oy oxiriga moslashtiriladi."""
    m = d.month - 1 + n
    y = d.year + m // 12
    m = m % 12 + 1
    day = day or d.day
    return date(y, m, min(day, calendar.monthrange(y, m)[1]))


def parse_date(text, today):
    """'bugun', 'ertaga', '15' (keyingi 15-sana), '15.10', '15.10.2026' -> date."""
    s = (text or "").strip().lower()
    if s == "bugun":
        return today
    if s == "ertaga":
        return today + timedelta(days=1)
    try:
        if re.fullmatch(r"\d{1,2}", s):
            day = int(s)
            if not 1 <= day <= 31:
                return None
            d = add_months(today.replace(day=1), 0, day)
            return d if d >= today else add_months(today.replace(day=1), 1, day)
        m = re.fullmatch(r"(\d{1,2})[./-](\d{1,2})(?:[./-](\d{2,4}))?", s)
        if m:
            day, month, year = m.groups()
            if year is None:
                d = date(today.year, int(month), int(day))
                return d if d >= today else date(today.year + 1, int(month), int(day))
            year = int(year)
            if year < 100:
                year += 2000
            return date(year, int(month), int(day))
    except ValueError:
        return None
    return None


# ---------- Hisobotlar ----------

def month_summary(user, year, month):
    income = expense = 0.0
    by_category = {}
    for t in user["transactions"]:
        d = date.fromisoformat(t["date"])
        if d.year != year or d.month != month:
            continue
        if t["type"] == INCOME:
            income += t["amount"]
        else:
            expense += t["amount"]
            by_category[t["category"]] = by_category.get(t["category"], 0) + t["amount"]
    return {
        "income": income,
        "expense": expense,
        "net": income - expense,
        "by_category": sorted(by_category.items(), key=lambda kv: -kv[1]),
    }


def active_debts(user):
    return [d for d in user["debts"] if not d.get("closed")]


def debt_totals(user):
    owe = owed = monthly = 0.0
    for d in active_debts(user):
        if d["kind"] == "owed_to_me":
            owed += d["remaining"]
        else:
            owe += d["remaining"]
            monthly += min(d.get("monthly", 0), d["remaining"])
    return {"owe": owe, "owed": owed, "monthly": monthly}


def debt_events(debt, end):
    """Kredit/qarz bo'yicha kutilayotgan to'lovlar (sana, summa) ro'yxati `end` sanasigacha."""
    if debt.get("closed") or not debt.get("next_due"):
        return []
    due = date.fromisoformat(debt["next_due"])
    remaining = debt["remaining"]
    monthly = debt.get("monthly", 0)
    if monthly <= 0:
        return [(due, remaining)] if due <= end else []
    events = []
    for i in range(math.ceil(remaining / monthly)):
        d = add_months(due, i, debt.get("due_day"))
        if d > end:
            break
        events.append((d, min(monthly, remaining - i * monthly)))
    return events


def planned_dates(item, end):
    start = date.fromisoformat(item["date"])
    if item.get("repeat") != "monthly":
        return [start] if start <= end else []
    dates, i = [], 0
    while True:
        d = add_months(start, i, item.get("day"))
        if d > end:
            return dates
        dates.append(d)
        i += 1


def upcoming(user, today, days=30):
    """Kutilayotgan daromad/chiqimlar (muddati o'tganlari ham) — sana bo'yicha tartiblangan."""
    end = today + timedelta(days=days)
    events = []
    for p in user["planned"]:
        for d in planned_dates(p, end):
            events.append({
                "date": d, "type": p["type"], "title": p["title"], "amount": p["amount"],
                "source": "planned", "id": p["id"], "overdue": d < today,
            })
    for debt in active_debts(user):
        kind_type = INCOME if debt["kind"] == "owed_to_me" else EXPENSE
        for d, amount in debt_events(debt, end):
            events.append({
                "date": d, "type": kind_type, "title": debt["name"], "amount": amount,
                "source": "debt", "id": debt["id"], "overdue": d < today,
            })
    events.sort(key=lambda e: (e["date"], e["type"] != EXPENSE))
    return events


def forecast(user, today, days=30):
    ev = upcoming(user, today, days)
    inflow = sum(e["amount"] for e in ev if e["type"] == INCOME)
    outflow = sum(e["amount"] for e in ev if e["type"] == EXPENSE)
    return {"in": inflow, "out": outflow, "net": inflow - outflow}


def month_end_forecast(user, today):
    """Shu oy hozirgacha bo'lgan natija + oy oxirigacha kutilayotganlar."""
    s = month_summary(user, today.year, today.month)
    last_day = date(today.year, today.month, calendar.monthrange(today.year, today.month)[1])
    f = forecast(user, today, (last_day - today).days)
    return s["net"] + f["net"]


# ---------- O'zgartirishlar ----------

def new_id(user):
    i = user["next_id"]
    user["next_id"] += 1
    return i


def add_transaction(user, tx_type, amount, category, today, note=""):
    tx = {
        "id": new_id(user), "type": tx_type, "amount": amount,
        "category": category, "note": note, "date": today.isoformat(),
    }
    user["transactions"].append(tx)
    return tx


def pay_debt(user, debt, amount, today, advance):
    """To'lovni qayd qiladi: qoldiqni kamaytiradi, tranzaksiya yozadi, kerak bo'lsa keyingi sanani suradi."""
    amount = min(amount, debt["remaining"])
    debt["remaining"] = round(debt["remaining"] - amount, 2)
    debt.setdefault("payments", []).append({"date": today.isoformat(), "amount": amount})
    if debt["kind"] == "owed_to_me":
        add_transaction(user, INCOME, amount, DEBT_RETURN_CATEGORY, today, debt["name"])
    else:
        add_transaction(user, EXPENSE, amount, DEBT_PAYMENT_CATEGORY, today, debt["name"])
    if debt["remaining"] <= 0:
        debt["closed"] = True
    elif advance and debt.get("next_due"):
        debt["next_due"] = add_months(date.fromisoformat(debt["next_due"]), 1, debt.get("due_day")).isoformat()
    return amount


def complete_planned(user, item, today):
    """Rejalashtirilgan to'lovni bajarilgan deb belgilaydi."""
    add_transaction(user, item["type"], item["amount"], item.get("category") or item["title"], today, item["title"])
    if item.get("repeat") == "monthly":
        item["date"] = add_months(date.fromisoformat(item["date"]), 1, item.get("day")).isoformat()
    else:
        user["planned"].remove(item)
