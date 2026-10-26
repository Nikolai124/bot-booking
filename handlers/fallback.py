from aiogram import Router
from aiogram.types import CallbackQuery, Message

import keyboards as kb

router = Router()


@router.callback_query()
async def stale_button(callback: CallbackQuery) -> None:
    # Кнопки из старых сообщений — иначе у пользователя будут бесконечно крутиться часики
    await callback.answer("Эта кнопка устарела. Начни заново: /start", show_alert=True)


@router.message()
async def unknown_message(message: Message) -> None:
    await message.answer("Не понял 🤔 Пользуйся кнопками внизу или нажми /start", reply_markup=kb.main_menu())
