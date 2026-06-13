"""Entry point for the Telegram bot: `python -m bot`."""
from __future__ import annotations

import asyncio

from aiogram import Bot, Dispatcher

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from bot.handlers import router

_logger = get_logger(__name__)


async def run() -> None:
    """Configure and start long-polling the Telegram bot."""
    configure_logging()
    settings = get_settings()
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not configured.")

    bot = Bot(token=settings.telegram_bot_token)
    dispatcher = Dispatcher()
    dispatcher.include_router(router)

    _logger.info("bot_starting", api_base_url=settings.api_base_url)
    try:
        await dispatcher.start_polling(bot)
    finally:
        await bot.session.close()


def main() -> None:
    """Synchronous wrapper used as the module entry point."""
    asyncio.run(run())


if __name__ == "__main__":
    main()
