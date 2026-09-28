import os
from datetime import datetime, timedelta, timezone

TOKEN = os.getenv('TOKEN')
ADMIN_CODE = os.getenv('ADMIN_CODE')  # bo'sh bo'lsa bot hamma uchun ochiq

# Railway'da ma'lumot o'chib ketmasligi uchun Volume ulab, DATA_PATH=/data/database.json qiling
DATA_PATH = os.getenv('DATA_PATH', 'database.json')

TZ = timezone(timedelta(hours=int(os.getenv('TZ_OFFSET', '5'))))  # Toshkent: UTC+5
REMIND_HOUR = int(os.getenv('REMIND_HOUR', '9'))  # har kuni eslatma soati


def today():
    return datetime.now(TZ).date()
