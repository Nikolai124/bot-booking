"""Запись: услуга → дата → время → телефон (если ещё не знаем) → подтверждение."""

import html
import logging
import re
from contextlib import suppress
from datetime import date, datetime

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

import config
import db
import keyboards as kb
from keyboards import DateCb, NavCb, ServiceCb, SlotCb, fmt_day, fmt_dt
from slots import available_dates, free_slots

router = Router()
log = logging.getLogger(__name__)


class Booking(StatesGroup):
    service = State()
    day = State()
    slot = State()
    phone = State()
    confirm = State()


def normalize_phone(raw: str) -> str | None:
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 11 and digits[0] in "78":
        return "+7" + digits[1:]
    if len(digits) == 10:
        return "+7" + digits
    return None


async def edit(callback: CallbackQuery, text: str, markup=None) -> None:
    with suppress(TelegramBadRequest):
        await callback.message.edit_text(text, reply_markup=markup)
    await callback.answer()


# ---------- 1. Услуга ----------
@router.message(F.text == kb.BTN_BOOK)
async def start_booking(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(Booking.service)
    await message.answer("Выбери услугу:", reply_markup=kb.services())


@router.callback_query(NavCb.filter(F.to == "services"))
async def back_to_services(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Booking.service)
    await edit(callback, "Выбери услугу:", kb.services())


@router.callback_query(Booking.service, ServiceCb.filter())
async def choose_service(callback: CallbackQuery, callback_data: ServiceCb, state: FSMContext) -> None:
    if callback_data.code not in config.SERVICES_BY_CODE:
        await callback.answer("Такой услуги больше нет", show_alert=True)
        return
    await state.update_data(service=callback_data.code)
    await show_dates(callback, state)


# ---------- 2. Дата ----------
async def show_dates(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    service = config.SERVICES_BY_CODE[data["service"]]
    await state.set_state(Booking.day)
    await edit(callback, f"<b>{service.title}</b>\n\nВыбери день:", kb.dates(available_dates()))


@router.callback_query(Booking.slot, NavCb.filter(F.to == "dates"))
async def back_to_dates(callback: CallbackQuery, state: FSMContext) -> None:
    await show_dates(callback, state)


@router.callback_query(Booking.day, DateCb.filter())
async def choose_day(callback: CallbackQuery, callback_data: DateCb, state: FSMContext) -> None:
    day = date.fromisoformat(callback_data.day)
    if day not in available_dates():
        await callback.answer("На этот день записи нет", show_alert=True)
        return

    data = await state.get_data()
    service = config.SERVICES_BY_CODE[data["service"]]
    times = free_slots(day, service.minutes, await db.busy_intervals(day))
    if not times:
        await callback.answer("На этот день всё занято, выбери другой 🙏", show_alert=True)
        return

    await state.update_data(day=callback_data.day)
    await state.set_state(Booking.slot)
    await edit(callback, f"<b>{service.title}</b>, {fmt_day(day)}\n\nВыбери время:", kb.slots(times))


# ---------- 3. Время ----------
@router.callback_query(Booking.slot, SlotCb.filter())
async def choose_slot(callback: CallbackQuery, callback_data: SlotCb, state: FSMContext) -> None:
    data = await state.get_data()
    start_at = datetime.strptime(f"{data['day']} {callback_data.time}", "%Y-%m-%d %H%M")
    await state.update_data(start_at=start_at.isoformat())

    phone = await db.last_phone(callback.from_user.id)
    if phone:
        await state.update_data(phone=phone)
        await show_confirm(callback.message, state, edit_message=True)
        await callback.answer()
        return

    await state.set_state(Booking.phone)
    with suppress(TelegramBadRequest):
        await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        "Оставь номер, чтобы мастер мог связаться с тобой. Нажми кнопку ниже или напиши номер.",
        reply_markup=kb.phone_keyboard(),
    )
    await callback.answer()


# ---------- 4. Телефон ----------
@router.message(Booking.phone, F.contact)
async def phone_from_contact(message: Message, state: FSMContext) -> None:
    if message.contact.user_id != message.from_user.id:
        await message.answer("Отправь, пожалуйста, свой номер кнопкой ниже.")
        return
    await save_phone(message, state, message.contact.phone_number)


@router.message(Booking.phone, F.text)
async def phone_from_text(message: Message, state: FSMContext) -> None:
    await save_phone(message, state, message.text)


async def save_phone(message: Message, state: FSMContext, raw: str) -> None:
    phone = normalize_phone(raw)
    if not phone:
        await message.answer("Не похоже на номер. Пример: +7 900 123-45-67")
        return
    await state.update_data(phone=phone)
    await message.answer("Номер сохранили 👌", reply_markup=kb.main_menu())
    await show_confirm(message, state)


# ---------- 5. Подтверждение ----------
async def show_confirm(message: Message, state: FSMContext, edit_message: bool = False) -> None:
    data = await state.get_data()
    service = config.SERVICES_BY_CODE[data["service"]]
    start_at = datetime.fromisoformat(data["start_at"])
    text = (
        "Проверь запись:\n\n"
        f"✂️ {service.title}\n"
        f"🗓 {fmt_dt(start_at)}\n"
        f"💰 {service.price} ₽\n"
        f"📱 {data['phone']}"
    )
    await state.set_state(Booking.confirm)
    if edit_message:
        with suppress(TelegramBadRequest):
            await message.edit_text(text, reply_markup=kb.confirm())
            return
    await message.answer(text, reply_markup=kb.confirm())


@router.callback_query(Booking.confirm, NavCb.filter(F.to == "abort"))
async def abort(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await edit(callback, "Запись отменена. Можно начать заново кнопкой «Записаться».")


@router.callback_query(Booking.confirm, NavCb.filter(F.to == "confirm"))
async def confirm(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    service = config.SERVICES_BY_CODE[data["service"]]
    start_at = datetime.fromisoformat(data["start_at"])

    # Время могло пройти, пока клиент думал
    if start_at not in free_slots(start_at.date(), service.minutes, []):
        await state.set_state(Booking.day)
        await edit(callback, "Это время уже недоступно, выбери другое:", kb.dates(available_dates()))
        return

    booking = await db.create_booking(
        user_id=callback.from_user.id,
        client_name=callback.from_user.full_name[:100],
        phone=data["phone"],
        service=service,
        start_at=start_at,
    )
    if booking is None:
        await state.set_state(Booking.day)
        await edit(callback, "Упс, это время только что заняли 😔 Выбери другое:", kb.dates(available_dates()))
        return

    await state.clear()
    await edit(
        callback,
        f"Готово, ты записан ✅\n\n✂️ {service.title}\n🗓 {fmt_dt(start_at)}\n📍 {config.ADDRESS}\n\n"
        "Напомним заранее. Отменить запись можно в «Мои записи».",
    )
    await notify_admin(bot, callback, booking)


async def notify_admin(bot: Bot, callback: CallbackQuery, booking: db.Booking) -> None:
    user = callback.from_user
    username = f"@{user.username}" if user.username else f'<a href="tg://user?id={user.id}">профиль</a>'
    try:
        await bot.send_message(
            config.ADMIN_ID,
            "🆕 <b>Новая запись</b>\n\n"
            f"{booking.service_title}, {booking.price} ₽\n"
            f"🗓 {fmt_dt(booking.start_at)}\n"
            f"👤 {html.escape(booking.client_name)}, {booking.phone}, {username}",
        )
    except Exception:
        log.exception("Не удалось уведомить админа")
