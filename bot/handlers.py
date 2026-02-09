"""Telegram bot command and message handlers"""
import logging
from telegram import Update
from telegram.ext import ContextTypes
from bot.nlp import parse_user_message
from bot.formatters import format_listings_for_telegram, format_analysis_summary
from database import (
    get_listings,
    get_runs,
    get_analysis,
    update_user_context,
    mark_listing_shown,
    get_recently_shown_listings,
    get_listing_by_reference
)
from config import Config

logger = logging.getLogger(__name__)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    user_id = update.effective_user.id

    # Security: Check if user is the owner
    if user_id != Config.BOT_OWNER_ID:
        await update.message.reply_text("Sorry, this bot is private.")
        return

    welcome = """👋 Welcome to your Rent Scraper Bot!

I can help you find and analyze rental properties. Try:

• "Show me new flats under £1500"
• "What did you recommend yesterday?"
• "Tell me more about the second one"
• /latest - See newest listings
• /analysis - Latest AI analysis
• /help - All commands

Just chat with me naturally! I'll remember our conversation."""

    await update.message.reply_text(welcome)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command"""
    help_text = """🤖 **Bot Commands**

**Quick Actions:**
/latest - Show newest listings
/analysis - Latest Claude analysis

**Natural Language:**
Just chat with me! Examples:
• "Show flats under £1600 in Camden"
• "What about 2 bedrooms?"
• "Tell me about the first one"
• "What's new today?"

**Follow-ups:**
I remember our conversation, so you can ask:
• "What about the second property?"
• "Show me more like that"
• "Tell me about property 3"

**Tips:**
• I keep context from today's chats
• Ask about properties from previous recommendations
• Change your search criteria anytime"""

    await update.message.reply_text(help_text, parse_mode="Markdown")


async def latest_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show latest listings"""
    user_id = update.effective_user.id

    # Get newest listings
    listings = get_listings(
        filters={},
        sort="first_seen_at",
        order="DESC",
        limit=Config.MAX_LISTINGS_PER_MESSAGE
    )

    if not listings:
        await update.message.reply_text("No listings found yet. The scraper will run at 5 AM daily!")
        return

    # Format and send with detailed=True to show more info
    formatted = format_listings_for_telegram(listings, detailed=True)
    await update.message.reply_text(formatted, parse_mode="HTML", disable_web_page_preview=True)

    # Track shown listings with position numbers
    for position, listing in enumerate(listings, start=1):
        mark_listing_shown(user_id, listing["id"], position, "latest_command")


async def analysis_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show latest Claude analysis"""
    user_id = update.effective_user.id

    # Get most recent run
    runs = get_runs(limit=1)
    if not runs:
        await update.message.reply_text("No analysis yet. Run a scrape first!")
        return

    run = runs[0]
    analysis = get_analysis(run["id"])

    if not analysis:
        await update.message.reply_text(f"Run #{run['id']} completed but no analysis available.")
        return

    # Get all listings to create a map for URL lookup
    all_listings = get_listings(filters={}, sort="first_seen_at", order="DESC", limit=200)
    listings_map = {str(listing["rightmove_id"]): listing for listing in all_listings}

    # Format analysis with listings map for URLs
    formatted = format_analysis_summary(analysis, listings_map)
    await update.message.reply_text(formatted, parse_mode="HTML", disable_web_page_preview=True)

    # Update context - user is now looking at this analysis
    update_user_context(user_id, f"analysis_{run['id']}", {"run_id": run["id"]})


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle natural language messages"""
    user_id = update.effective_user.id

    # Security check
    if user_id != Config.BOT_OWNER_ID:
        return

    message_text = update.message.text

    try:
        # Parse message with Claude (includes conversation context)
        intent_data = await parse_user_message(user_id, message_text)

        # Route based on intent
        if intent_data["intent"] == "search":
            await handle_search_query(update, user_id, intent_data)

        elif intent_data["intent"] == "follow_up":
            await handle_follow_up(update, user_id, intent_data)

        elif intent_data["intent"] == "analysis":
            await handle_analysis_request(update, user_id, intent_data)

        else:
            # General conversation
            response = intent_data.get("user_friendly_response", "I'm here to help! Try asking about properties.")
            await update.message.reply_text(response)

    except Exception as e:
        logger.error(f"Message handling error: {e}", exc_info=True)
        await update.message.reply_text("Sorry, I had trouble understanding. Try rephrasing or use /help!")


async def handle_search_query(update, user_id, intent_data):
    """Handle property search queries"""
    entities = intent_data.get("entities", {})

    # Build filters from entities
    filters = {}
    if entities.get("price_min"):
        filters["min_price"] = entities["price_min"]
    if entities.get("price_max"):
        filters["max_price"] = entities["price_max"]
    if entities.get("bedrooms"):
        filters["bedrooms"] = entities["bedrooms"]

    # Query database
    listings = get_listings(
        filters=filters,
        sort="first_seen_at",
        order="DESC",
        limit=Config.MAX_LISTINGS_PER_MESSAGE
    )

    if not listings:
        await update.message.reply_text("No properties match those criteria. Try adjusting your search!")
        return

    # Send formatted results
    formatted = format_listings_for_telegram(listings, query_context=entities)
    await update.message.reply_text(formatted, parse_mode="HTML", disable_web_page_preview=True)

    # Track shown listings for follow-ups WITH POSITION NUMBERS
    for position, listing in enumerate(listings, start=1):
        mark_listing_shown(user_id, listing["id"], position, f"search: {entities}")

    # Update user context
    update_user_context(user_id, "search_results", {"filters": filters, "count": len(listings)})


async def handle_follow_up(update, user_id, intent_data):
    """Handle follow-up queries about previously shown listings"""
    reference = intent_data.get("reference", {})

    # Get the position number Claude extracted (e.g., "second one" = 2)
    position = reference.get("listing_index", 1)

    # Use the database function to get listing by reference number
    target_listing = get_listing_by_reference(user_id, position, hours=24)

    if not target_listing:
        await update.message.reply_text(f"I can't find property #{position}. Try asking about 'property 1', 'property 2', etc.")
        return

    # Send detailed view
    formatted = format_listings_for_telegram([target_listing], detailed=True)
    response_text = intent_data.get("user_friendly_response", f"Here's more about property #{position}:")

    await update.message.reply_text(f"{response_text}\n\n{formatted}", parse_mode="HTML", disable_web_page_preview=True)


async def handle_analysis_request(update, user_id, intent_data):
    """Handle requests for analysis/recommendations"""
    # Redirect to analysis command
    await analysis_command(update, None)
