import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo

BASE_DIR = Path(__file__).resolve().parent


def load_dotenv(path: Path) -> None:
    """Читает .env для локального запуска. На Render переменные задаются в панели."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_dotenv(BASE_DIR / ".env")

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0") or 0)
DATABASE_URL = os.getenv("DATABASE_URL") or f"sqlite+aiosqlite:///{BASE_DIR / 'bookings.db'}"

WEBHOOK_BASE = os.getenv("WEBHOOK_BASE") or os.getenv("RENDER_EXTERNAL_URL", "")
WEBHOOK_PATH = "/webhook"
PORT = int(os.getenv("PORT", "8080"))
# Telegram принимает в секрете только буквы, цифры, _ и -. Хэшируем, чтобы подошла любая строка
WEBHOOK_SECRET = hashlib.sha256(os.getenv("WEBHOOK_SECRET", BOT_TOKEN).encode()).hexdigest()

# ---------- Настройки бизнеса ----------
BUSINESS_NAME = "Барбершоп «Борода»"
ADDRESS = "ул. Пушкина, 10"
PHONE = "+7 (000) 000-00-00"

TZ = ZoneInfo("Europe/Moscow")
WORK_START_HOUR = 10       # первая запись в 10:00
WORK_END_HOUR = 20         # услуга должна закончиться до 20:00
SLOT_STEP_MINUTES = 30     # шаг сетки времени
DAYS_AHEAD = 14            # на сколько дней вперёд можно записаться
DAYS_OFF = {0}             # выходные: 0 — понедельник, 6 — воскресенье
MIN_LEAD_MINUTES = 60      # не раньше чем через час от текущего времени
REMIND_BEFORE_HOURS = 24   # за сколько часов напомнить о записи


@dataclass(frozen=True)
class Service:
    code: str
    title: str
    minutes: int
    price: int


SERVICES = [
    Service("cut", "Мужская стрижка", 60, 1500),
    Service("beard", "Оформление бороды", 30, 800),
    Service("combo", "Стрижка + борода", 90, 2100),
    Service("kids", "Детская стрижка", 30, 1000),
    Service("buzz", "Стрижка машинкой", 30, 700),
]
SERVICES_BY_CODE = {service.code: service for service in SERVICES}

if not BOT_TOKEN:
    raise SystemExit("Не задан BOT_TOKEN. Скопируй .env.example в .env и впиши токен.")
