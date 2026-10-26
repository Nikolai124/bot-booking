from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

import config
import keyboards as kb

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        f"Привет! Это бот <b>{config.BUSINESS_NAME}</b> ✂️\n\n"
        "Здесь можно записаться на стрижку, посмотреть цены и отменить запись. "
        "Жми кнопку внизу 👇",
        reply_markup=kb.main_menu(),
    )


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Ок, запись отменили. Возвращаю в меню.", reply_markup=kb.main_menu())


@router.message(F.text == kb.BTN_PRICES)
async def prices(message: Message) -> None:
    lines = [f"• {s.title} — <b>{s.price} ₽</b> ({s.minutes} мин)" for s in config.SERVICES]
    await message.answer("💈 <b>Услуги и цены</b>\n\n" + "\n".join(lines))


@router.message(F.text == kb.BTN_CONTACTS)
async def contacts(message: Message) -> None:
    days_off = ", ".join(kb.WEEKDAYS[d] for d in sorted(config.DAYS_OFF)) or "нет"
    await message.answer(
        f"📍 <b>{config.BUSINESS_NAME}</b>\n\n"
        f"Адрес: {config.ADDRESS}\n"
        f"Телефон: {config.PHONE}\n"
        f"Работаем с {config.WORK_START_HOUR}:00 до {config.WORK_END_HOUR}:00, выходной: {days_off}"
    )

