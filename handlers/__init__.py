from aiogram import Router

from . import booking, common, fallback, manage


def get_router() -> Router:
    router = Router()
    # Порядок важен: команды и кнопки меню должны срабатывать раньше шагов записи,
    # иначе «/start», набранный на шаге телефона, бот примет за номер
    router.include_routers(common.router, manage.router, booking.router, fallback.router)
    return router
