"""Telegram bot handlerlari: menyu, daromad/chiqim, kreditlar, kutilayotganlar, hisobotlar."""
import re
from datetime import date

from aiogram import F, Router
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup,
    KeyboardButton, Message, ReplyKeyboardMarkup,
)

import finance as fn
from config import today
from jsondb import JsonDB
from report import build_month_pdf

router = Router()

BTN_EXP = "➖ Chiqim"
BTN_INC = "➕ Daromad"
BTN_DEBTS = "💳 Kredit va qarzlar"
BTN_PLAN = "📅 Kutilayotganlar"
BTN_REPORT = "📊 Hisobot"
BTN_HISTORY = "📋 Tarix"
BTN_PDF = "📄 PDF hisobot"
BTN_HELP = "❓ Yordam"
BTN_CANCEL = "❌ Bekor qilish"


def main_kb():
    rows = [[BTN_EXP, BTN_INC], [BTN_DEBTS, BTN_PLAN], [BTN_REPORT, BTN_HISTORY], [BTN_PDF, BTN_HELP]]
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=t) for t in row] for row in rows], resize_keyboard=True,
    )


def cancel_kb():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=BTN_CANCEL)]], resize_keyboard=True)


def ikb(rows):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=text, callback_data=data) for text, data in row] for row in rows
    ])


HELP_TEXT = (
    "<b>Moliya nazorati boti</b>\n\n"
    "<b>Tezkor yozish</b> (menyusiz):\n"
    "<code>-45000 ovqat</code> — chiqim\n"
    "<code>+5mln oylik</code> — daromad\n"
    "Summa: <code>50000</code>, <code>50 000</code>, <code>50k</code>, <code>1.5mln</code>\n\n"
    f"<b>{BTN_DEBTS}</b> — bank kreditlari, siz olgan va sizga berilishi kerak bo'lgan qarzlar. "
    "Har oylik to'lovni bir tugma bilan belgilaysiz, qoldiq avtomatik kamayadi.\n"
    f"<b>{BTN_PLAN}</b> — aniq kutilayotgan to'lovlar va tushumlar (ijara, kommunal, oylik...). "
    "Bir martalik yoki har oylik bo'lishi mumkin.\n"
    f"<b>{BTN_REPORT}</b> — shu oy natijasi, qarzlar va 30 kunlik prognoz.\n\n"
    "Har kuni ertalab muddati yaqinlashgan to'lovlar haqida eslatma keladi. "
    "O'chirish/yoqish: /eslatma\n"
    "Istalgan vaqtda bekor qilish: /cancel"
)


# ---------- Umumiy ----------

@router.message(CommandStart())
async def cmd_start(msg: Message, state: FSMContext):
    await state.clear()
    await msg.answer(
        "Assalomu alaykum! Men daromad, chiqim, kredit va qarzlaringizni nazorat qilaman.\n\n" + HELP_TEXT,
        reply_markup=main_kb(),
    )


@router.message(Command("help"))
@router.message(F.text == BTN_HELP)
async def cmd_help(msg: Message, state: FSMContext):
    await state.clear()
    await msg.answer(HELP_TEXT, reply_markup=main_kb())


@router.message(Command("cancel"))
@router.message(F.text == BTN_CANCEL)
async def cmd_cancel(msg: Message, state: FSMContext):
    await state.clear()
    await msg.answer("Bekor qilindi.", reply_markup=main_kb())


@router.message(Command("eslatma"))
async def cmd_remind(msg: Message, db: JsonDB):
    u = db.user(msg.from_user.id)
    u["settings"]["remind"] = not u["settings"].get("remind", True)
    db.save()
    await msg.answer("🔔 Eslatmalar yoqildi." if u["settings"]["remind"] else "🔕 Eslatmalar o'chirildi.")


# ---------- Daromad / chiqim ----------

class TxForm(StatesGroup):
    amount = State()
    category = State()


def _tx_saved_text(user, tx):
    s = fn.month_summary(user, today().year, today().month)
    label = "Chiqim" if tx["type"] == fn.EXPENSE else "Daromad"
    return (
        f"✅ {label} saqlandi: <b>{fn.fmt_money(tx['amount'])}</b> — {tx['category']}"
        + (f" ({tx['note']})" if tx.get("note") else "")
        + f"\n\nShu oy: daromad {fn.fmt_money(s['income'])}, chiqim {fn.fmt_money(s['expense'])}"
    )


@router.message(F.text.in_({BTN_EXP, BTN_INC}))
async def tx_start(msg: Message, state: FSMContext):
    await state.clear()
    tx_type = fn.EXPENSE if msg.text == BTN_EXP else fn.INCOME
    await state.update_data(type=tx_type)
    await state.set_state(TxForm.amount)
    await msg.answer("Summani kiriting (masalan: 50000, 50k, 1.5mln):", reply_markup=cancel_kb())


@router.message(TxForm.amount)
async def tx_amount(msg: Message, state: FSMContext):
    amount = fn.parse_amount(msg.text)
    if amount is None:
        await msg.answer("Summani tushunmadim. Masalan: 50000 yoki 50k")
        return
    data = await state.update_data(amount=amount)
    cats = fn.EXPENSE_CATEGORIES if data["type"] == fn.EXPENSE else fn.INCOME_CATEGORIES
    rows = [[(c, f"cat:{i}") for i, c in enumerate(cats[j:j + 2], start=j)] for j in range(0, len(cats), 2)]
    await state.set_state(TxForm.category)
    await msg.answer("Kategoriyani tanlang yoki o'zingiz yozing:", reply_markup=ikb(rows))


async def _save_tx(target: Message, state: FSMContext, db: JsonDB, uid: int, category: str):
    data = await state.get_data()
    await state.clear()
    user = db.user(uid)
    tx = fn.add_transaction(user, data["type"], data["amount"], category, today())
    db.save()
    await target.answer(_tx_saved_text(user, tx), reply_markup=main_kb())


@router.callback_query(TxForm.category, F.data.startswith("cat:"))
async def tx_category_cb(cb: CallbackQuery, state: FSMContext, db: JsonDB):
    data = await state.get_data()
    cats = fn.EXPENSE_CATEGORIES if data["type"] == fn.EXPENSE else fn.INCOME_CATEGORIES
    category = cats[int(cb.data.split(":")[1])]
    await cb.message.edit_reply_markup(reply_markup=None)
    await _save_tx(cb.message, state, db, cb.from_user.id, category)
    await cb.answer()


@router.message(TxForm.category)
async def tx_category_text(msg: Message, state: FSMContext, db: JsonDB):
    await _save_tx(msg, state, db, msg.from_user.id, msg.text.strip()[:40])


# ---------- Kreditlar va qarzlar ----------

class DebtForm(StatesGroup):
    name = State()
    amount = State()
    monthly = State()
    due = State()


class PayForm(StatesGroup):
    amount = State()


def _debt_line(d):
    icon = "🟢" if d["kind"] == "owed_to_me" else "🔴"
    line = f"{icon} <b>{d['name']}</b> — {fn.fmt_money(d['remaining'])}"
    if d.get("monthly"):
        line += f", oyiga {fn.fmt_money(d['monthly'])}"
    if d.get("next_due"):
        line += f", keyingi: {fn.fmt_date(d['next_due'])}"
    return line


def _debts_view(user):
    debts = fn.active_debts(user)
    t = fn.debt_totals(user)
    lines = ["<b>💳 Kredit va qarzlar</b>\n"]
    for kind, label in fn.DEBT_KINDS.items():
        items = [d for d in debts if d["kind"] == kind]
        if items:
            lines.append(f"<b>{label}:</b>")
            lines += [_debt_line(d) for d in items]
            lines.append("")
    if not debts:
        lines.append("Hozircha kredit yoki qarz yo'q.\n")
    lines.append(f"Men qarzdorman: <b>{fn.fmt_money(t['owe'])}</b>")
    lines.append(f"Menga qarzdor: <b>{fn.fmt_money(t['owed'])}</b>")
    lines.append(f"Oylik majburiy to'lovlar: <b>{fn.fmt_money(t['monthly'])}</b>")
    rows = [[(f"{d['name']} — {fn.fmt_money(d['remaining'])}", f"d:open:{d['id']}")] for d in debts]
    rows.append([("➕ Yangi kredit/qarz", "debts:new")])
    return "\n".join(lines), ikb(rows)


def _debt_detail(d):
    lines = [
        f"<b>{d['name']}</b> ({fn.DEBT_KINDS[d['kind']]})",
        f"Boshlang'ich summa: {fn.fmt_money(d['total'])}",
        f"Qoldiq: <b>{fn.fmt_money(d['remaining'])}</b>",
        f"To'langan: {fn.fmt_money(d['total'] - d['remaining'])} "
        f"({(d['total'] - d['remaining']) / d['total'] * 100:.0f}%)",
    ]
    if d.get("monthly"):
        left = -(-d["remaining"] // d["monthly"])
        lines.append(f"Oylik to'lov: {fn.fmt_money(d['monthly'])} (taxminan {left:.0f} oy qoldi)")
    if d.get("next_due"):
        lines.append(f"Keyingi muddat: {fn.fmt_date(d['next_due'])}")
    for p in d.get("payments", [])[-5:]:
        lines.append(f"  • {fn.fmt_date(p['date'])}: {fn.fmt_money(p['amount'])}")
    rows = []
    if d.get("monthly"):
        rows.append([(f"✅ Oylik to'lov ({fn.fmt_money(min(d['monthly'], d['remaining']))})", f"d:paym:{d['id']}")])
    pay_label = "✍️ Qaytardi (summa)" if d["kind"] == "owed_to_me" else "✍️ Boshqa summa to'lash"
    rows.append([(pay_label, f"d:payc:{d['id']}")])
    rows.append([("🗑 O'chirish", f"d:del:{d['id']}"), ("⬅️ Orqaga", "debts:list")])
    return "\n".join(lines), ikb(rows)


def _find(items, item_id):
    return next((x for x in items if x["id"] == item_id), None)


@router.message(F.text == BTN_DEBTS)
async def debts_list(msg: Message, state: FSMContext, db: JsonDB):
    await state.clear()
    text, kb = _debts_view(db.user(msg.from_user.id))
    await msg.answer(text, reply_markup=kb)


@router.callback_query(F.data == "debts:list")
async def debts_list_cb(cb: CallbackQuery, db: JsonDB):
    text, kb = _debts_view(db.user(cb.from_user.id))
    await cb.message.edit_text(text, reply_markup=kb)
    await cb.answer()


@router.callback_query(F.data == "debts:new")
async def debt_new(cb: CallbackQuery):
    rows = [[(label, f"dk:{kind}")] for kind, label in fn.DEBT_KINDS.items()]
    await cb.message.answer("Turini tanlang:", reply_markup=ikb(rows))
    await cb.answer()


@router.callback_query(F.data.startswith("dk:"))
async def debt_kind(cb: CallbackQuery, state: FSMContext):
    kind = cb.data.split(":")[1]
    await state.clear()
    await state.update_data(kind=kind)
    await state.set_state(DebtForm.name)
    hint = {"credit": "Bank va kredit nomi (masalan: Kapitalbank avtokredit)",
            "i_owe": "Kimdan qarz olgansiz? (ism)",
            "owed_to_me": "Kim sizdan qarz? (ism)"}[kind]
    await cb.message.edit_reply_markup(reply_markup=None)
    await cb.message.answer(hint + ":", reply_markup=cancel_kb())
    await cb.answer()


@router.message(DebtForm.name)
async def debt_name(msg: Message, state: FSMContext):
    await state.update_data(name=msg.text.strip()[:40])
    await state.set_state(DebtForm.amount)
    await msg.answer("Hozirgi qoldiq summa qancha? (to'lanishi kerak bo'lgan summa)")


@router.message(DebtForm.amount)
async def debt_amount(msg: Message, state: FSMContext):
    amount = fn.parse_amount(msg.text)
    if amount is None:
        await msg.answer("Summani tushunmadim. Masalan: 12000000 yoki 12mln")
        return
    await state.update_data(amount=amount)
    await state.set_state(DebtForm.monthly)
    await msg.answer("Oylik to'lov summasi? (grafik bo'lmasa <code>0</code> yozing)")


@router.message(DebtForm.monthly)
async def debt_monthly(msg: Message, state: FSMContext):
    text = msg.text.strip()
    monthly = 0.0 if text in {"0", "-"} else fn.parse_amount(text)
    if monthly is None:
        await msg.answer("Summani tushunmadim. Oylik to'lov yoki 0 yozing.")
        return
    await state.update_data(monthly=monthly)
    await state.set_state(DebtForm.due)
    if monthly:
        await msg.answer("Keyingi to'lov sanasi? (masalan: <code>15</code>, <code>15.10</code> yoki <code>15.10.2026</code>)")
    else:
        await msg.answer("Qaytarish muddati? (sana yoki muddat bo'lmasa <code>-</code>)")


@router.message(DebtForm.due)
async def debt_due(msg: Message, state: FSMContext, db: JsonDB):
    data = await state.get_data()
    text = msg.text.strip()
    due = None
    if text != "-" or data["monthly"]:
        due = fn.parse_date(text, today())
        if due is None:
            await msg.answer("Sanani tushunmadim. Masalan: 15 yoki 15.10.2026")
            return
    user = db.user(msg.from_user.id)
    debt = {
        "id": fn.new_id(user), "kind": data["kind"], "name": data["name"],
        "total": data["amount"], "remaining": data["amount"], "monthly": data["monthly"],
        "due_day": due.day if due else None, "next_due": due.isoformat() if due else None,
        "created": today().isoformat(), "payments": [], "closed": False,
    }
    user["debts"].append(debt)
    db.save()
    await state.clear()
    await msg.answer("✅ Saqlandi.", reply_markup=main_kb())
    text, kb = _debt_detail(debt)
    await msg.answer(text, reply_markup=kb)


@router.callback_query(F.data.startswith("d:"))
async def debt_action(cb: CallbackQuery, state: FSMContext, db: JsonDB):
    _, action, raw_id = cb.data.split(":")
    user = db.user(cb.from_user.id)
    debt = _find(user["debts"], int(raw_id))
    if debt is None or debt.get("closed"):
        await cb.answer("Topilmadi", show_alert=True)
        return
    if action == "open":
        text, kb = _debt_detail(debt)
        await cb.message.edit_text(text, reply_markup=kb)
    elif action == "paym":
        paid = fn.pay_debt(user, debt, debt["monthly"], today(), advance=True)
        db.save()
        await _after_payment(cb.message, debt, paid)
    elif action == "payc":
        await state.clear()
        await state.update_data(debt_id=debt["id"])
        await state.set_state(PayForm.amount)
        await cb.message.answer(f"{debt['name']}: qancha summa?", reply_markup=cancel_kb())
    elif action == "del":
        await cb.message.edit_text(
            f"<b>{debt['name']}</b> o'chirilsinmi? (to'lovlar tarixi amallarda qoladi)",
            reply_markup=ikb([[("Ha, o'chirish", f"d:delok:{debt['id']}"), ("Yo'q", f"d:open:{debt['id']}")]]),
        )
    elif action == "delok":
        user["debts"].remove(debt)
        db.save()
        text, kb = _debts_view(user)
        await cb.message.edit_text(text, reply_markup=kb)
    await cb.answer()


async def _after_payment(target: Message, debt, paid):
    text = f"✅ {fn.fmt_money(paid)} qayd qilindi."
    if debt.get("closed"):
        await target.answer(text + f"\n🎉 <b>{debt['name']}</b> to'liq yopildi!", reply_markup=main_kb())
        return
    await target.answer(text, reply_markup=main_kb())
    detail, kb = _debt_detail(debt)
    await target.answer(detail, reply_markup=kb)


@router.message(PayForm.amount)
async def pay_custom(msg: Message, state: FSMContext, db: JsonDB):
    amount = fn.parse_amount(msg.text)
    if amount is None:
        await msg.answer("Summani tushunmadim.")
        return
    data = await state.get_data()
    await state.clear()
    user = db.user(msg.from_user.id)
    debt = _find(user["debts"], data["debt_id"])
    if debt is None or debt.get("closed"):
        await msg.answer("Topilmadi.", reply_markup=main_kb())
        return
    advance = bool(debt.get("monthly")) and amount >= debt["monthly"]
    paid = fn.pay_debt(user, debt, amount, today(), advance=advance)
    db.save()
    await _after_payment(msg, debt, paid)


# ---------- Kutilayotgan (rejalashtirilgan) daromad/chiqimlar ----------

class PlanForm(StatesGroup):
    title = State()
    amount = State()
    date = State()
    repeat = State()


def _event_line(e):
    sign = "➕" if e["type"] == fn.INCOME else "➖"
    mark = "⚠️ " if e["overdue"] else ""
    src = " 💳" if e["source"] == "debt" else ""
    return f"{mark}{fn.fmt_date(e['date'])} {sign} {e['title']}{src} — <b>{fn.fmt_money(e['amount'])}</b>"


def _plan_view(user):
    t = today()
    events = fn.upcoming(user, t, 30)
    f = fn.forecast(user, t, 30)
    lines = ["<b>📅 Keyingi 30 kun</b>\n"]
    lines += [_event_line(e) for e in events] or ["Kutilayotgan to'lov yo'q."]
    lines += [
        "",
        f"Kutilayotgan tushum: <b>{fn.fmt_money(f['in'])}</b>",
        f"Kutilayotgan chiqim: <b>{fn.fmt_money(f['out'])}</b>",
        f"Farq: <b>{fn.fmt_money(f['net'])}</b>",
    ]
    if any(e["overdue"] for e in events):
        lines.append("\n⚠️ — muddati o'tgan, bajarilgan bo'lsa belgilang.")
    rows = []
    for p in sorted(user["planned"], key=lambda p: p["date"]):
        sign = "➕" if p["type"] == fn.INCOME else "➖"
        rep = " 🔁" if p.get("repeat") == "monthly" else ""
        rows.append([(f"{sign} {p['title']} ({fn.fmt_date(p['date'])}){rep}", f"p:open:{p['id']}")])
    rows.append([("➕ Yangi kutilayotgan to'lov/tushum", "plan:new")])
    return "\n".join(lines), ikb(rows)


def _plan_detail(p):
    kind = "Daromad" if p["type"] == fn.INCOME else "Chiqim"
    rep = "har oy" if p.get("repeat") == "monthly" else "bir martalik"
    text = (
        f"<b>{p['title']}</b>\n{kind}, {rep}\n"
        f"Summa: <b>{fn.fmt_money(p['amount'])}</b>\nSana: {fn.fmt_date(p['date'])}"
    )
    done = "✅ Keldi" if p["type"] == fn.INCOME else "✅ To'landi"
    return text, ikb([
        [(done, f"p:done:{p['id']}")],
        [("🗑 O'chirish", f"p:del:{p['id']}"), ("⬅️ Orqaga", "plan:list")],
    ])


@router.message(F.text == BTN_PLAN)
async def plan_list(msg: Message, state: FSMContext, db: JsonDB):
    await state.clear()
    text, kb = _plan_view(db.user(msg.from_user.id))
    await msg.answer(text, reply_markup=kb)


@router.callback_query(F.data == "plan:list")
async def plan_list_cb(cb: CallbackQuery, db: JsonDB):
    text, kb = _plan_view(db.user(cb.from_user.id))
    await cb.message.edit_text(text, reply_markup=kb)
    await cb.answer()


@router.callback_query(F.data == "plan:new")
async def plan_new(cb: CallbackQuery):
    await cb.message.answer("Nima kutilyapti?", reply_markup=ikb([
        [("➖ Chiqim (to'lov)", f"pt:{fn.EXPENSE}"), ("➕ Daromad (tushum)", f"pt:{fn.INCOME}")],
    ]))
    await cb.answer()


@router.callback_query(F.data.startswith("pt:"))
async def plan_type(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.update_data(type=cb.data.split(":")[1])
    await state.set_state(PlanForm.title)
    await cb.message.edit_reply_markup(reply_markup=None)
    await cb.message.answer("Nomi? (masalan: Ijara, Kommunal, Oylik maosh)", reply_markup=cancel_kb())
    await cb.answer()


@router.message(PlanForm.title)
async def plan_title(msg: Message, state: FSMContext):
    await state.update_data(title=msg.text.strip()[:40])
    await state.set_state(PlanForm.amount)
    await msg.answer("Summa?")


@router.message(PlanForm.amount)
async def plan_amount(msg: Message, state: FSMContext):
    amount = fn.parse_amount(msg.text)
    if amount is None:
        await msg.answer("Summani tushunmadim.")
        return
    await state.update_data(amount=amount)
    await state.set_state(PlanForm.date)
    await msg.answer("Qaysi sanada? (<code>bugun</code>, <code>ertaga</code>, <code>10</code>, <code>10.11</code>, <code>10.11.2026</code>)")


@router.message(PlanForm.date)
async def plan_date(msg: Message, state: FSMContext):
    d = fn.parse_date(msg.text, today())
    if d is None:
        await msg.answer("Sanani tushunmadim. Masalan: 10 yoki 10.11.2026")
        return
    await state.update_data(date=d.isoformat())
    await state.set_state(PlanForm.repeat)
    await msg.answer("Takrorlanadimi?", reply_markup=ikb([[("Bir martalik", "pr:once"), ("🔁 Har oy", "pr:monthly")]]))


@router.callback_query(PlanForm.repeat, F.data.startswith("pr:"))
async def plan_repeat(cb: CallbackQuery, state: FSMContext, db: JsonDB):
    data = await state.get_data()
    await state.clear()
    user = db.user(cb.from_user.id)
    d = date.fromisoformat(data["date"])
    item = {
        "id": fn.new_id(user), "type": data["type"], "title": data["title"], "amount": data["amount"],
        "date": d.isoformat(), "day": d.day, "repeat": cb.data.split(":")[1],
    }
    user["planned"].append(item)
    db.save()
    await cb.message.edit_reply_markup(reply_markup=None)
    await cb.message.answer("✅ Saqlandi. Muddatidan oldin eslataman.", reply_markup=main_kb())
    text, kb = _plan_view(user)
    await cb.message.answer(text, reply_markup=kb)
    await cb.answer()


@router.callback_query(F.data.startswith("p:"))
async def plan_action(cb: CallbackQuery, db: JsonDB):
    _, action, raw_id = cb.data.split(":")
    user = db.user(cb.from_user.id)
    item = _find(user["planned"], int(raw_id))
    if item is None:
        await cb.answer("Topilmadi", show_alert=True)
        return
    if action == "open":
        text, kb = _plan_detail(item)
        await cb.message.edit_text(text, reply_markup=kb)
    elif action == "done":
        fn.complete_planned(user, item, today())
        db.save()
        await cb.answer(f"✅ {fn.fmt_money(item['amount'])} amallarga yozildi")
        text, kb = _plan_view(user)
        await cb.message.edit_text(text, reply_markup=kb)
        return
    elif action == "del":
        user["planned"].remove(item)
        db.save()
        text, kb = _plan_view(user)
        await cb.message.edit_text(text, reply_markup=kb)
    await cb.answer()


# ---------- Hisobot va tarix ----------

def report_text(user):
    t = today()
    s = fn.month_summary(user, t.year, t.month)
    debts = fn.debt_totals(user)
    f = fn.forecast(user, t, 30)
    lines = [
        f"<b>📊 Hisobot — {t.strftime('%m.%Y')}</b>\n",
        f"Daromad: <b>{fn.fmt_money(s['income'])}</b>",
        f"Chiqim: <b>{fn.fmt_money(s['expense'])}</b>",
        f"Natija: <b>{fn.fmt_money(s['net'])}</b>",
        f"Oy oxirigacha prognoz: <b>{fn.fmt_money(fn.month_end_forecast(user, t))}</b>",
    ]
    if s["by_category"]:
        lines.append("\n<b>Chiqimlar:</b>")
        for cat, amount in s["by_category"]:
            lines.append(f"  {cat}: {fn.fmt_money(amount)} ({amount / s['expense'] * 100:.0f}%)")
    lines += [
        "\n<b>Qarzlar:</b>",
        f"  Men qarzdorman: {fn.fmt_money(debts['owe'])}",
        f"  Menga qarzdor: {fn.fmt_money(debts['owed'])}",
        f"  Oylik majburiy to'lov: {fn.fmt_money(debts['monthly'])}",
        "\n<b>Keyingi 30 kun:</b>",
        f"  Kutilayotgan tushum: {fn.fmt_money(f['in'])}",
        f"  Kutilayotgan chiqim: {fn.fmt_money(f['out'])}",
    ]
    if s["income"] and debts["monthly"]:
        ratio = debts["monthly"] / s["income"] * 100
        warn = " ⚠️ yuqori (40% dan oshmagani ma'qul)" if ratio > 40 else ""
        lines.append(f"\nKredit yuki: daromadning {ratio:.0f}%{warn}")
    return "\n".join(lines)


@router.message(Command("hisobot"))
@router.message(F.text == BTN_REPORT)
async def report(msg: Message, state: FSMContext, db: JsonDB):
    await state.clear()
    await msg.answer(report_text(db.user(msg.from_user.id)), reply_markup=main_kb())


def _history_text(user):
    txs = user["transactions"][-15:]
    if not txs:
        return "Hali amal yo'q."
    lines = ["<b>📋 Oxirgi amallar</b>\n"]
    for t in reversed(txs):
        sign = "➕" if t["type"] == fn.INCOME else "➖"
        note = f" ({t['note']})" if t.get("note") else ""
        lines.append(f"{fn.fmt_date(t['date'])} {sign} {fn.fmt_money(t['amount'])} — {t['category']}{note}")
    return "\n".join(lines)


@router.message(F.text == BTN_HISTORY)
async def history(msg: Message, state: FSMContext, db: JsonDB):
    await state.clear()
    user = db.user(msg.from_user.id)
    kb = ikb([[("🗑 Oxirgisini o'chirish", "tx:dellast")]]) if user["transactions"] else None
    await msg.answer(_history_text(user), reply_markup=kb)


@router.callback_query(F.data == "tx:dellast")
async def history_del_last(cb: CallbackQuery, db: JsonDB):
    user = db.user(cb.from_user.id)
    if user["transactions"]:
        tx = user["transactions"].pop()
        db.save()
        await cb.answer(f"O'chirildi: {fn.fmt_money(tx['amount'])} — {tx['category']}", show_alert=True)
        kb = ikb([[("🗑 Oxirgisini o'chirish", "tx:dellast")]]) if user["transactions"] else None
        await cb.message.edit_text(_history_text(user), reply_markup=kb)
    else:
        await cb.answer("Amal yo'q")


@router.message(F.text == BTN_PDF)
async def pdf_report(msg: Message, state: FSMContext, db: JsonDB):
    await state.clear()
    t = today()
    data = build_month_pdf(db.user(msg.from_user.id), t)
    await msg.answer_document(BufferedInputFile(data, filename=f"hisobot_{t.strftime('%Y_%m')}.pdf"))


# ---------- Tezkor yozish: "-45000 ovqat", "+5mln oylik" ----------

QUICK_RE = re.compile(r"^\s*([+-])\s*([\d\s.,]+(?:k|ming|mln|million|m)?)\b\s*(.*)$", re.IGNORECASE)


@router.message(StateFilter(None), F.text.regexp(QUICK_RE))
async def quick_entry(msg: Message, db: JsonDB):
    sign, raw_amount, rest = QUICK_RE.match(msg.text).groups()
    amount = fn.parse_amount(raw_amount)
    if amount is None:
        await msg.answer("Summani tushunmadim. Masalan: <code>-45000 ovqat</code>")
        return
    tx_type = fn.INCOME if sign == "+" else fn.EXPENSE
    cats = fn.INCOME_CATEGORIES if tx_type == fn.INCOME else fn.EXPENSE_CATEGORIES
    rest = rest.strip()
    category = next((c for c in cats if rest and c.lower().startswith(rest.split()[0].lower())), None)
    user = db.user(msg.from_user.id)
    tx = fn.add_transaction(user, tx_type, amount, category or (rest[:40] or "Boshqa"), today())
    db.save()
    await msg.answer(_tx_saved_text(user, tx), reply_markup=main_kb())


@router.message(StateFilter(None))
async def fallback(msg: Message):
    await msg.answer("Menyudan tanlang yoki tezkor yozing: <code>-45000 ovqat</code>", reply_markup=main_kb())
