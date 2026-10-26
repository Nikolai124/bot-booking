from datetime import date, datetime

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

import config

WEEKDAYS = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
MONTHS = ["янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"]

BTN_BOOK = "📅 Записаться"
BTN_MY = "🗂 Мои записи"
BTN_PRICES = "💈 Услуги и цены"
BTN_CONTACTS = "📍 Контакты"


def fmt_day(day: date) -> str:
    return f"{WEEKDAYS[day.weekday()]}, {day.day} {MONTHS[day.month - 1]}"


def fmt_dt(moment: datetime) -> str:
    return f"{fmt_day(moment.date())} в {moment:%H:%M}"


class ServiceCb(CallbackData, prefix="svc"):
    code: str


class DateCb(CallbackData, prefix="day"):
    day: str  # 2026-10-20


class SlotCb(CallbackData, prefix="slot"):
    time: str  # 1030


class NavCb(CallbackData, prefix="nav"):
    to: str  # services | dates | confirm | abort


class CancelCb(CallbackData, prefix="cancel"):
    booking_id: int
    by_admin: bool = False


class AdminDayCb(CallbackData, prefix="aday"):
    day: str


def main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_BOOK)],
            [KeyboardButton(text=BTN_MY), KeyboardButton(text=BTN_PRICES)],
            [KeyboardButton(text=BTN_CONTACTS)],
        ],
        resize_keyboard=True,
    )


def phone_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Отправить мой номер", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def services():
    kb = InlineKeyboardBuilder()
    for service in config.SERVICES:
        kb.button(
            text=f"{service.title} · {service.minutes} мин · {service.price} ₽",
            callback_data=ServiceCb(code=service.code),
        )
    kb.adjust(1)
    return kb.as_markup()


def dates(days: list[date]):
    kb = InlineKeyboardBuilder()
    for day in days:
        kb.button(text=fmt_day(day), callback_data=DateCb(day=day.isoformat()))
    kb.adjust(3)
    kb.row(InlineKeyboardButton(text="⬅️ К услугам", callback_data=NavCb(to="services").pack()))
    return kb.as_markup()


def slots(times: list[datetime]):
    kb = InlineKeyboardBuilder()
    for moment in times:
        kb.button(text=f"{moment:%H:%M}", callback_data=SlotCb(time=f"{moment:%H%M}"))
    kb.adjust(4)
    kb.row(InlineKeyboardButton(text="⬅️ Другая дата", callback_data=NavCb(to="dates").pack()))
    return kb.as_markup()


def confirm():
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Записаться", callback_data=NavCb(to="confirm"))
    kb.button(text="❌ Отмена", callback_data=NavCb(to="abort"))
    kb.adjust(2)
    return kb.as_markup()


def my_bookings(bookings):
    kb = InlineKeyboardBuilder()
    for booking in bookings:
        kb.button(
            text=f"❌ Отменить {fmt_dt(booking.start_at)}",
            callback_data=CancelCb(booking_id=booking.id),
        )
    kb.adjust(1)
    return kb.as_markup()


def admin_days(days: list[date], bookings):
    kb = InlineKeyboardBuilder()
    for booking in bookings:
        kb.button(
            text=f"❌ {booking.start_at:%H:%M} {booking.client_name}",
            callback_data=CancelCb(booking_id=booking.id, by_admin=True),
        )
    for day in days:
        kb.button(text=fmt_day(day), callback_data=AdminDayCb(day=day.isoformat()))
    # Каждая запись на своей строке, дни — по три в ряд
    kb.adjust(*([1] * len(bookings)), 3)
    return kb.as_markup()
