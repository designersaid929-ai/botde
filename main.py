import sys
import logging
import asyncio

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot.config import config
from bot.handlers import setup_routers
from bot.services.instagram import instagram_service


def configure_logging():
    """Sets up standard application logging."""
    logging.basicConfig(
        level=getattr(logging, config.LOG_LEVEL, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )
    # Quiet overly chatty libraries
    logging.getLogger("aiogram.event").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


async def main():
    """Bot entrypoint."""
    configure_logging()
    logger = logging.getLogger("main")

    logger.info("Initializing Instagram Telegram Bot...")

    # Initialize stats database
    from bot.services import stats
    await stats.init_db()

    # Validate bot token
    try:
        config.validate()
    except ValueError as ve:
        logger.error(str(ve))
        logger.error("Please copy .env.example to .env and insert your TELEGRAM_BOT_TOKEN.")
        sys.exit(1)

    # Report Instagram authentication status
    is_logged_in, ig_user = instagram_service.check_session_status()
    if is_logged_in:
        logger.info(f"Instagram session: ACTIVE (Authenticated as @{ig_user})")
    else:
        logger.warning(
            "Instagram session: ANONYMOUS. Story downloads require an authenticated session. "
            "To enable stories, configure INSTAGRAM_SESSION_ID in your .env file."
        )

    # Report Gemini AI status
    from bot.services.ai import gemini_service
    if gemini_service.is_configured:
        logger.info(f"Gemini AI: ACTIVE (Model: {config.GEMINI_MODEL})")
    else:
        logger.warning(
            "Gemini AI: INACTIVE. Set GEMINI_API_KEY in .env or via /setkey to enable AI Chat."
        )

    # Initialize Bot and Dispatcher
    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher()

    # Register handlers
    setup_routers(dp)

    logger.info("Bot handlers registered successfully.")

    try:
        # Drop pending updates so old queries aren't processed on startup
        await bot.delete_webhook(drop_pending_updates=True)
        bot_info = await bot.get_me()
        logger.info(f"Bot started successfully! Running as @{bot_info.username} (ID: {bot_info.id})")
        logger.info("Waiting for user messages...")

        await dp.start_polling(bot)
    except Exception as e:
        logger.critical(f"Fatal error while running bot: {e}", exc_info=True)
    finally:
        logger.info("Shutting down bot session...")
        await bot.session.close()
        logger.info("Bot shutdown complete.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot stopped by user.")
