#!/usr/bin/env python3
"""
Standalone script to run the rent scraper and save results.
Designed to work in GitHub Actions without Flask or database.
"""
import os
import json
import logging
from datetime import datetime
from scraper import run_scrape

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def send_telegram_notification(message, bot_token, chat_id):
    """Send a message via Telegram bot."""
    import requests
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    try:
        response = requests.post(url, json={
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML",
        })
        response.raise_for_status()
        logger.info("Telegram notification sent successfully")
    except Exception as e:
        logger.error(f"Failed to send Telegram notification: {e}")


def main():
    # Default search settings
    settings = {
        "location_display_name": "London",
        "location_identifier": "REGION%5E87490",
        "min_price": 1300,
        "max_price": 1750,
        "min_bedrooms": 1,
        "max_bedrooms": 1,
        "property_type": "flat",
        "radius": 3.0,
        "max_days_since_added": 1,
        "include_let_agreed": True,
    }

    logger.info("Starting rent scraper...")
    logger.info(f"Settings: {json.dumps(settings, indent=2)}")

    # Run scraper
    results = run_scrape(settings)

    # Save results to JSON
    output = {
        "timestamp": datetime.utcnow().isoformat(),
        "settings": settings,
        "total_found": results["total_found"],
        "errors": results["errors"],
        "properties": results["properties"],
    }

    output_file = "scrape_results.json"
    with open(output_file, "w") as f:
        json.dump(output, f, indent=2)

    logger.info(f"Results saved to {output_file}")
    logger.info(f"Found {results['total_found']} properties with {results['errors']} errors")

    # Send Telegram notification if configured
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if bot_token and chat_id:
        new_listings = [p for p in results["properties"] if p]

        if new_listings:
            # Send summary
            message = f"🏠 <b>Rent Scraper Update</b>\n\n"
            message += f"Found <b>{len(new_listings)}</b> properties\n\n"

            # Add top 5 listings
            for i, listing in enumerate(new_listings[:5]):
                message += f"{i+1}. {listing.get('display_price', 'N/A')} - "
                message += f"{listing.get('bedrooms', '?')} bed - "
                message += f"{listing.get('display_address', 'Unknown')}\n"
                message += f"   {listing.get('url', '')}\n\n"

            if len(new_listings) > 5:
                message += f"...and {len(new_listings) - 5} more properties"

            send_telegram_notification(message, bot_token, chat_id)
        else:
            logger.info("No new listings found, skipping notification")
    else:
        logger.info("Telegram not configured, skipping notification")


if __name__ == "__main__":
    main()
