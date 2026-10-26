"""Расчёт свободного времени. Чистые функции без базы и Telegram, их легко проверить."""

from datetime import date, datetime, timedelta

import config


def now_local() -> datetime:
    # Время храним «наивным» в часовом поясе салона, так проще и в SQLite, и в PostgreSQL
    return datetime.now(config.TZ).replace(tzinfo=None, second=0, microsecond=0)


def available_dates(today: date | None = None) -> list[date]:
    today = today or now_local().date()
    days = (today + timedelta(days=offset) for offset in range(config.DAYS_AHEAD))
    return [day for day in days if day.weekday() not in config.DAYS_OFF]


def free_slots(
    day: date,
    duration_minutes: int,
    busy: list[tuple[datetime, datetime]],
    now: datetime | None = None,
) -> list[datetime]:
    """Все времена начала, в которые услуга помещается в рабочий день и не пересекается с записями."""
    now = now or now_local()
    earliest = now + timedelta(minutes=config.MIN_LEAD_MINUTES)
    duration = timedelta(minutes=duration_minutes)
    step = timedelta(minutes=config.SLOT_STEP_MINUTES)

    start = datetime.combine(day, datetime.min.time()).replace(hour=config.WORK_START_HOUR)
    day_end = start.replace(hour=config.WORK_END_HOUR)

    result = []
    while start + duration <= day_end:
        end = start + duration
        overlaps = any(start < busy_end and busy_start < end for busy_start, busy_end in busy)
        if start >= earliest and not overlaps:
            result.append(start)
        start += step
    return result
