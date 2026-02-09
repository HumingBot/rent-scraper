import os
from dotenv import load_dotenv

_dir = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(_dir, ".env"), override=True)


class Config:
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "6614531509")
    FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "dev-key-change-me")
    DATABASE_PATH = os.getenv("DATABASE_PATH", os.path.join(_dir, "rent_scraper.db"))


DEFAULT_SEARCH_SETTINGS = {
    "location_identifier": "REGION%5E87490",
    "location_display_name": "London",
    "min_price": 1300,
    "max_price": 1750,
    "min_bedrooms": 1,
    "max_bedrooms": 1,
    "property_type": "flat",
    "radius": 3.0,
    "max_days_since_added": 1,
    "include_let_agreed": True,
    "scheduler_hour": 5,
    "scheduler_minute": 0,
    "scheduler_enabled": True,
}
