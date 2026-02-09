"""Natural language processing with Claude for conversational bot"""
import json
import logging
from anthropic import Anthropic
from config import Config
from database import (
    get_conversation_history,
    save_conversation_turn,
    get_user_context,
    get_recently_shown_listings,
    get_analysis,
    clear_old_conversation_history
)

logger = logging.getLogger(__name__)

# Singleton Claude client (reuse from analyzer.py pattern)
_client = None

def get_client():
    global _client
    if _client is None:
        _client = Anthropic(api_key=Config.ANTHROPIC_API_KEY)
    return _client


CONVERSATION_SYSTEM_PROMPT = """You are a helpful rental property assistant for London properties.

The user is searching for rental flats and you help them by:
1. Understanding their natural language queries
2. Extracting search criteria (price, bedrooms, location, features)
3. Providing conversational responses about properties
4. **Maintaining context** - remembering previous recommendations and properties discussed

When the user asks follow-up questions like "what about the second one?" or "tell me more",
reference the conversation history to understand what they're referring to.

Return JSON:
{
  "intent": "search|analysis|follow_up|configuration|general",
  "entities": {
    "price_min": null,
    "price_max": 1500,
    "bedrooms": 1,
    "location": "Camden",
    "features": ["gym"]
  },
  "reference": {
    "refers_to_previous": true,
    "listing_index": 2,
    "analysis_id": 123
  },
  "user_friendly_response": "I'll show you the second property I recommended..."
}"""


async def parse_user_message(telegram_id, message):
    """Parse user message with full conversation context"""

    # Clear old context (daily reset)
    clear_old_conversation_history(telegram_id, days=1)

    # Get conversation history for context (today only)
    history = get_conversation_history(telegram_id, limit=Config.CONVERSATION_HISTORY_LIMIT)
    user_context = get_user_context(telegram_id)
    recent_listings = get_recently_shown_listings(telegram_id, hours=24)

    # Build messages for Claude
    messages = []

    # Add conversation history
    for turn in history[-6:]:  # Last 3 exchanges (6 messages)
        messages.append({
            "role": turn["role"],
            "content": turn["message"]
        })

    # Add context about recently shown listings
    if recent_listings:
        context_msg = f"\n\n[Context: Recently shown {len(recent_listings)} properties today, numbered 1-{len(recent_listings)}]"
        messages.append({
            "role": "user",
            "content": f"{message}{context_msg}"
        })
    else:
        messages.append({
            "role": "user",
            "content": message
        })

    try:
        response = get_client().messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1500,
            system=CONVERSATION_SYSTEM_PROMPT,
            messages=messages
        )

        # Parse JSON response
        content = response.content[0].text

        # Try to extract JSON (might be wrapped in markdown)
        if "```json" in content:
            json_str = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            json_str = content.split("```")[1].split("```")[0].strip()
        else:
            json_str = content

        result = json.loads(json_str)

        # Save this turn
        save_conversation_turn(telegram_id, "user", message)

        return result

    except Exception as e:
        logger.error(f"NL parsing failed: {e}")
        # Fallback to simple keyword matching
        return _simple_keyword_parse(message)


def _simple_keyword_parse(message):
    """Fallback keyword-based parsing if Claude fails"""
    message_lower = message.lower()

    intent = "general"
    if any(word in message_lower for word in ["search", "find", "show", "list"]):
        intent = "search"
    elif any(word in message_lower for word in ["analysis", "recommend", "best", "top"]):
        intent = "analysis"
    elif any(word in message_lower for word in ["second", "third", "first", "that one", "this one", "property 1", "property 2", "property 3"]):
        intent = "follow_up"
        # Try to extract position number
        position = 1
        if "first" in message_lower or "1" in message_lower:
            position = 1
        elif "second" in message_lower or "2" in message_lower:
            position = 2
        elif "third" in message_lower or "3" in message_lower:
            position = 3
        elif "fourth" in message_lower or "4" in message_lower:
            position = 4
        elif "fifth" in message_lower or "5" in message_lower:
            position = 5
        return {
            "intent": intent,
            "entities": {},
            "reference": {"refers_to_previous": True, "listing_index": position},
            "user_friendly_response": None
        }

    return {
        "intent": intent,
        "entities": {},
        "reference": {},
        "user_friendly_response": None
    }


async def generate_response(telegram_id, query_result, intent_data):
    """Generate conversational response with Claude"""

    # Get conversation history
    history = get_conversation_history(telegram_id, limit=6)

    # Build prompt for response generation
    response_prompt = f"""Generate a friendly, conversational response.

Query result: {len(query_result)} properties found
User intent: {intent_data.get('intent')}

Keep it concise and friendly. If showing properties, briefly describe why they match."""

    try:
        messages = []

        # Add recent history for context
        for turn in history[-4:]:
            messages.append({
                "role": turn["role"],
                "content": turn["message"]
            })

        messages.append({
            "role": "user",
            "content": response_prompt
        })

        response = get_client().messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            messages=messages
        )

        response_text = response.content[0].text

        # Save assistant's response
        save_conversation_turn(telegram_id, "assistant", response_text)

        return response_text

    except Exception as e:
        logger.error(f"Response generation failed: {e}")
        return "Here's what I found for you:"
