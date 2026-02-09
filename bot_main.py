"""Main entry point for Telegram bot"""
import os
import sys
import logging
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
)
from config import Config
from bot.handlers import (
    start_command,
    help_command,
    latest_command,
    analysis_command,
    handle_message,
)
from database import init_db

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    """Start the bot"""

    # Check configuration
    if not Config.TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not set in environment!")
        sys.exit(1)

    if not Config.BOT_OWNER_ID or Config.BOT_OWNER_ID == 0:
        logger.error("BOT_OWNER_ID not set! Set your Telegram user ID.")
        sys.exit(1)

    if not Config.ANTHROPIC_API_KEY:
        logger.error("ANTHROPIC_API_KEY not set! Claude integration requires API key.")
        sys.exit(1)

    # Initialize database
    logger.info("Initializing database...")
    init_db()

    # Create application
    logger.info("Creating bot application...")
    application = Application.builder().token(Config.TELEGRAM_BOT_TOKEN).build()

    # Register command handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("latest", latest_command))
    application.add_handler(CommandHandler("analysis", analysis_command))

    # Register message handler (for natural language)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Start bot
    logger.info(f"Starting bot in {Config.BOT_MODE} mode...")
    logger.info(f"Bot owner ID: {Config.BOT_OWNER_ID}")

    if Config.BOT_MODE == "polling":
        # Polling mode (simpler, works locally and in cloud)
        logger.info("Bot started in polling mode. Press Ctrl+C to stop.")
        application.run_polling(allowed_updates=["message"])

    elif Config.BOT_MODE == "webhook":
        # Webhook mode (for production with HTTPS)
        if not Config.BOT_WEBHOOK_URL:
            logger.error("BOT_WEBHOOK_URL required for webhook mode!")
            sys.exit(1)

        webhook_url = f"{Config.BOT_WEBHOOK_URL}/telegram/webhook"
        logger.info(f"Bot started in webhook mode: {webhook_url}")
        application.run_webhook(
            listen="0.0.0.0",
            port=8443,
            url_path="/telegram/webhook",
            webhook_url=webhook_url
        )

    else:
        logger.error(f"Unknown BOT_MODE: {Config.BOT_MODE}")
        sys.exit(1)


if __name__ == "__main__":
    main()
