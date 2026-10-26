"""Мои записи для клиента и /admin для мастера."""

import html
import logging
from contextlib import suppress
from datetime import date

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

import config
import db
import keyboards as kb
from keyboards import AdminDayCb, CancelCb, fmt_day, fmt_dt
from slots import available_dates, now_local

router = Router()
log = logging.getLogger(__name__)


def is_admin(user_id: int) -> bool:
    return user_id == config.ADMIN_ID


# ---------- Клиент ----------
async def my_bookings_view(user_id: int) -> tuple[str, object]:
    bookings = await db.user_bookings(user_id)
    if not bookings:
        return "У тебя нет предстоящих записей. Записаться — кнопка «📅 Записаться».", None
    lines = [f"• {fmt_dt(b.start_at)} — {b.service_title}" for b in bookings]
    return "🗂 <b>Твои записи</b>\n\n" + "\n".join(lines), kb.my_bookings(bookings)


@router.message(F.text == kb.BTN_MY)
async def my_bookings(message: Message) -> None:
    text, markup = await my_bookings_view(message.from_user.id)
    await message.answer(text, reply_markup=markup)


@router.callback_query(CancelCb.filter(F.by_admin.is_(False)))
async def cancel_by_client(callback: CallbackQuery, callback_data: CancelCb, bot: Bot) -> None:
    booking = await db.get_booking(callback_data.booking_id)
    # Проверяем владельца: callback_data можно подделать, чужую запись отменять нельзя
    if not booking or booking.user_id != callback.from_user.id:
        await callback.answer("Запись не найдена", show_alert=True)
        return

    booking = await db.cancel_booking(booking.id)
    if booking:
        await callback.answer("Запись отменена")
        with suppress(Exception):
            await bot.send_message(
                config.ADMIN_ID,
                f"🚫 Клиент отменил запись: {fmt_dt(booking.start_at)}, "
                f"{booking.service_title}, {html.escape(booking.client_name)}",
            )
    else:
        await callback.answer("Запись уже отменена")

    text, markup = await my_bookings_view(callback.from_user.id)
    with suppress(TelegramBadRequest):
        await callback.message.edit_text(text, reply_markup=markup)


# ---------- Мастер ----------
async def admin_day_view(day: date) -> tuple[str, object]:
    bookings = await db.day_bookings(day)
    days = available_dates()[:9]
    if bookings:
        lines = [
            f"<b>{b.start_at:%H:%M}–{b.end_at:%H:%M}</b> {b.service_title}\n"
            f"    {html.escape(b.client_name)}, {b.phone}"
            for b in bookings
        ]
        body = "\n".join(lines)
    else:
        body = "Записей нет."
    text = f"📋 <b>Записи на {fmt_day(day)}</b>\n\n{body}\n\nНажми на запись, чтобы отменить её."
    return text, kb.admin_days(days, bookings)


@router.message(Command("admin"))
async def admin(message: Message) -> None:
    if not is_admin(message.from_user.id):
        return
    text, markup = await admin_day_view(now_local().date())
    await message.answer(text, reply_markup=markup)


@router.callback_query(AdminDayCb.filter())
async def admin_day(callback: CallbackQuery, callback_data: AdminDayCb) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    text, markup = await admin_day_view(date.fromisoformat(callback_data.day))
    with suppress(TelegramBadRequest):
        await callback.message.edit_text(text, reply_markup=markup)
    await callback.answer()


@router.callback_query(CancelCb.filter(F.by_admin.is_(True)))
async def cancel_by_admin(callback: CallbackQuery, callback_data: CancelCb, bot: Bot) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return

    booking = await db.cancel_booking(callback_data.booking_id)
    if not booking:
        await callback.answer("Запись уже отменена")
        return

    await callback.answer("Отменено, клиент получит уведомление")
    try:
        await bot.send_message(
            booking.user_id,
            f"😔 К сожалению, мастер отменил твою запись на {fmt_dt(booking.start_at)} "
            f"({booking.service_title}). Выбери другое время: «📅 Записаться».",
        )
    except Exception:
        log.warning("Не удалось уведомить клиента %s об отмене", booking.user_id)

    text, markup = await admin_day_view(booking.start_at.date())
    with suppress(TelegramBadRequest):
        await callback.message.edit_text(text, reply_markup=markup)
