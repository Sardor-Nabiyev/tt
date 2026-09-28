"""Oylik PDF hisobot (fpdf 1.7.2 — faqat lotin-1 shriftlari, shuning uchun matn tozalanadi)."""
from datetime import date

from fpdf import FPDF

import finance as fn

_REPLACE = {"‘": "'", "’": "'", "ʻ": "'", "ʼ": "'", "`": "'", "—": "-", "–": "-", "«": '"', "»": '"'}


def _t(text):
    text = str(text)
    for a, b in _REPLACE.items():
        text = text.replace(a, b)
    return text.encode("latin-1", "ignore").decode("latin-1").strip()


def _money(x):
    return _t(fn.fmt_money(x))


class _PDF(FPDF):
    def heading(self, text):
        self.ln(4)
        self.set_font("Arial", "B", 13)
        self.cell(0, 8, _t(text), ln=1)

    def row(self, cells, widths, bold=False, fill=False):
        self.set_font("Arial", "B" if bold else "", 10)
        if fill:
            self.set_fill_color(230, 230, 230)
        for text, w in zip(cells, widths):
            align = "R" if text and (text.endswith("so'm") or text[0].isdigit()) else "L"
            self.cell(w, 7, _t(text)[:45], border=1, align=align, fill=fill)
        self.ln()


def build_month_pdf(user, today: date):
    s = fn.month_summary(user, today.year, today.month)
    totals = fn.debt_totals(user)

    pdf = _PDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 10, _t(f"Moliyaviy hisobot: {today.strftime('%m.%Y')}"), ln=1)
    pdf.set_font("Arial", "", 9)
    pdf.cell(0, 5, _t(f"Tuzilgan sana: {fn.fmt_date(today)}"), ln=1)

    pdf.heading("Shu oy")
    w = [95, 95]
    pdf.row(["Daromad", _money(s["income"])], w)
    pdf.row(["Chiqim", _money(s["expense"])], w)
    pdf.row(["Natija (daromad - chiqim)", _money(s["net"])], w, bold=True)
    pdf.row(["Oy oxirigacha prognoz", _money(fn.month_end_forecast(user, today))], w)

    if s["by_category"]:
        pdf.heading("Chiqimlar kategoriyalar bo'yicha")
        w = [95, 55, 40]
        pdf.row(["Kategoriya", "Summa", "Ulush"], w, bold=True, fill=True)
        for cat, amount in s["by_category"]:
            pdf.row([cat, _money(amount), f"{amount / s['expense'] * 100:.1f}%"], w)

    pdf.heading("Kreditlar va qarzlar")
    debts = fn.active_debts(user)
    if debts:
        w = [55, 35, 40, 30, 30]
        pdf.row(["Nomi", "Turi", "Qoldiq", "Oylik", "Keyingi"], w, bold=True, fill=True)
        for d in debts:
            pdf.row([
                d["name"], fn.DEBT_KINDS[d["kind"]], _money(d["remaining"]),
                _money(d["monthly"]) if d.get("monthly") else "-",
                fn.fmt_date(d["next_due"]) if d.get("next_due") else "-",
            ], w)
    pdf.row(["Men qarzdorman (jami)", _money(totals["owe"])], [95, 95], bold=True)
    pdf.row(["Menga qarzdor (jami)", _money(totals["owed"])], [95, 95], bold=True)

    pdf.heading("Keyingi 30 kunda kutilayotganlar")
    events = fn.upcoming(user, today, 30)
    if events:
        w = [30, 25, 85, 50]
        pdf.row(["Sana", "Turi", "Nomi", "Summa"], w, bold=True, fill=True)
        for e in events:
            kind = "Daromad" if e["type"] == fn.INCOME else "Chiqim"
            title = e["title"] + (" (muddati o'tgan)" if e["overdue"] else "")
            pdf.row([fn.fmt_date(e["date"]), kind, title, _money(e["amount"])], w)
    else:
        pdf.set_font("Arial", "", 10)
        pdf.cell(0, 7, _t("Yo'q"), ln=1)

    month_tx = [t for t in user["transactions"] if t["date"][:7] == today.isoformat()[:7]]
    if month_tx:
        pdf.heading("Shu oydagi amallar")
        w = [30, 25, 50, 50, 35]
        pdf.row(["Sana", "Turi", "Kategoriya", "Izoh", "Summa"], w, bold=True, fill=True)
        for t in sorted(month_tx, key=lambda t: t["date"]):
            kind = "Daromad" if t["type"] == fn.INCOME else "Chiqim"
            pdf.row([fn.fmt_date(t["date"]), kind, t["category"], t.get("note", ""), _money(t["amount"])], w)

    out = pdf.output(dest="S")
    return out.encode("latin-1") if isinstance(out, str) else bytes(out)
