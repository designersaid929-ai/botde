from aiogram import Dispatcher
from bot.handlers.common import router as common_router
from bot.handlers.ai import router as ai_router
from bot.handlers.posts import router as posts_router
from bot.handlers.stories import router as stories_router
from bot.handlers.profile import router as profile_router


def setup_routers(dp: Dispatcher) -> None:
    """Registers all bot routers in proper evaluation order."""
    dp.include_router(common_router)
    dp.include_router(ai_router)
    dp.include_router(posts_router)
    dp.include_router(stories_router)
    dp.include_router(profile_router)

