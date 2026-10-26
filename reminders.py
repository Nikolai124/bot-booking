"""Фоновая задача: раз в минуту ищет записи, о которых пора напомнить."""

import asyncio
import logging

from aiogram import Bot

import config
import db
from keyboards import fmt_dt

log = logging.getLogger(__name__)


async def reminder_loop(bot: Bot) -> None:
    while True:
        try:
            for booking in await db.due_reminders():
                try:
                    await bot.send_message(
                        booking.user_id,
                        f"⏰ Напоминаем: {fmt_dt(booking.start_at)} у тебя {booking.service_title.lower()}.\n"
                        f"📍 {config.ADDRESS}\n\nЕсли не получается прийти, отмени запись в «Мои записи».",
                    )
                except Exception:
                    # Клиент мог заблокировать бота — не повторяем напоминание бесконечно
                    log.warning("Не удалось отправить напоминание клиенту %s", booking.user_id)
                await db.mark_reminded(booking.id)
        except Exception:
            log.exception("Ошибка в цикле напоминаний")
        await asyncio.sleep(60)
