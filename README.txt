MOLIYA NAZORATI BOTI (Telegram)
================================
Daromad, chiqim, kredit/qarzlar va aniq kutilayotgan to'lov/tushumlarni nazorat qiladi.

IMKONIYATLAR
- ➖ Chiqim / ➕ Daromad — summa + kategoriya. Tezkor yozish: "-45000 ovqat", "+5mln oylik"
- 💳 Kredit va qarzlar — bank kreditlari, siz olgan qarzlar, sizga qaytarilishi kerak qarzlar.
  Oylik to'lovni bir tugma bilan belgilaysiz: qoldiq kamayadi, keyingi sana suriladi,
  to'lov chiqim sifatida avtomatik yoziladi.
- 📅 Kutilayotganlar — ijara, kommunal, oylik maosh kabi aniq to'lov/tushumlar
  (bir martalik yoki har oy). 30 kunlik ro'yxat, muddati o'tganlar ⚠️ bilan.
- 📊 Hisobot — shu oy natijasi, kategoriyalar, qarzlar, 30 kunlik prognoz, kredit yuki %.
- 📄 PDF hisobot, 📋 Tarix (oxirgi amalni o'chirish mumkin).
- 🔔 Har kuni ertalab (REMIND_HOUR) yaqin 3 kun va muddati o'tgan to'lovlar eslatmasi. /eslatma — yoqish/o'chirish.

FAYLLAR TUZILISHI
- bot.py      — ishga tushirish, kirish kodi (ADMIN_CODE), kundalik eslatmalar
- handlers.py — Telegram menyu va dialoglar
- finance.py  — hisob-kitob mantiqi (summalar, sanalar, prognoz, to'lovlar)
- report.py   — PDF hisobot
- jsondb.py   — JSON faylda saqlash
- config.py   — sozlamalar (muhit o'zgaruvchilari)

RAILWAY'GA JOYLASH
1. Railway'da 'New Project' → 'Deploy from GitHub Repo' → shu repo.
2. 'Variables' bo'limiga qo'shing:
   TOKEN       — @BotFather bergan token (majburiy)
   ADMIN_CODE  — kirish kodi (botdan faqat siz foydalanishingiz uchun; bo'sh bo'lsa hamma uchun ochiq)
   DATA_PATH   — /data/database.json (pastga qarang)
   TZ_OFFSET   — 5 (Toshkent, standart)
   REMIND_HOUR — 9 (eslatma soati, standart)
3. MUHIM: Railway har deploy'da fayllarni tozalaydi. Ma'lumot o'chmasligi uchun
   servisga Volume qo'shing (mount path: /data) va DATA_PATH=/data/database.json qiling.
4. Logs bo'limida 'Polling started' chiqishini kuting, botga /start yozing.
