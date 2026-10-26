"""Точка входа. Локально бот работает через polling, на Render — через вебхук."""

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand, BotCommandScopeChat
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

import config
import db
from handlers import get_router
from reminders import reminder_loop

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logging.getLogger("aiohttp.access").setLevel(logging.WARNING)

# Держим ссылки на фоновые задачи, иначе сборщик мусора может их прибить
background_tasks: set[asyncio.Task] = set()


async def on_startup(bot: Bot) -> None:
    await db.init_db()
    commands = [
        BotCommand(command="start", description="Главное меню"),
        BotCommand(command="cancel", description="Прервать запись"),
    ]
    await bot.set_my_commands(commands)
    if config.ADMIN_ID:
        # Мастеру в меню команд показываем ещё и /admin
        await bot.set_my_commands(
            commands + [BotCommand(command="admin", description="Записи по дням")],
            scope=BotCommandScopeChat(chat_id=config.ADMIN_ID),
        )
    background_tasks.add(asyncio.create_task(reminder_loop(bot)))


def create_bot_and_dispatcher() -> tuple[Bot, Dispatcher]:
    bot = Bot(config.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.include_router(get_router())
    dp.startup.register(on_startup)
    return bot, dp


async def run_polling() -> None:
    bot, dp = create_bot_and_dispatcher()
    await bot.delete_webhook(drop_pending_updates=True)
    logging.info("Бот запущен в режиме polling")
    await dp.start_polling(bot)


def run_webhook() -> None:
    bot, dp = create_bot_and_dispatcher()

    async def set_webhook(bot: Bot) -> None:
        await bot.set_webhook(
            config.WEBHOOK_BASE.rstrip("/") + config.WEBHOOK_PATH,
            secret_token=config.WEBHOOK_SECRET,
            drop_pending_updates=True,
        )
        logging.info("Вебхук установлен")

    dp.startup.register(set_webhook)

    app = web.Application()
    # Главная страница нужна Render для проверки, что сервис живой
    app.router.add_get("/", lambda request: web.Response(text="Bot is running"))
    SimpleRequestHandler(dispatcher=dp, bot=bot, secret_token=config.WEBHOOK_SECRET).register(
        app, path=config.WEBHOOK_PATH
    )
    setup_application(app, dp, bot=bot)
    web.run_app(app, host="0.0.0.0", port=config.PORT)


if __name__ == "__main__":
    if config.WEBHOOK_BASE:
        run_webhook()
    else:
        asyncio.run(run_polling())
