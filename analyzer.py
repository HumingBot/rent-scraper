import json
import logging
from anthropic import Anthropic
from config import Config

logger = logging.getLogger(__name__)

client = None


def _get_client():
    global client
    if client is None:
        client = Anthropic(api_key=Config.ANTHROPIC_API_KEY)
    return client


ANALYSIS_SYSTEM_PROMPT = """You are a London rental property analyst. You will receive a list of rental property listings. Rank the top 5 properties based on these criteria:

**Must-haves (weighted heavily):**
- Monthly rent within the specified price range
- Good transport links (proximity to Tube/bus, Zone 1-3 preferred)
- Safe neighbourhood
- Modern/well-maintained property

**Nice-to-haves (bonus points):**
- Gym included or nearby
- Bills included (council tax, utilities, internet)
- Furnished or part-furnished
- Natural light / good-sized rooms

For each of your top 5, provide:
1. The property's Rightmove ID
2. A rank (1 = best)
3. A brief reasoning (2-3 sentences) explaining why you ranked it there

Respond in valid JSON with this structure:
{
  "rankings": [
    {
      "rightmove_id": "...",
      "rank": 1,
      "address": "...",
      "price": "...",
      "reasoning": "..."
    }
  ],
  "summary": "A 2-3 sentence overall summary of what's available today."
}"""


def format_listings_for_claude(listings):
    """Format property listings into structured text for the prompt."""
    parts = []
    for i, listing in enumerate(listings, 1):
        features = listing.get("key_features", "[]")
        if isinstance(features, str):
            try:
                features = json.loads(features)
            except json.JSONDecodeError:
                features = []

        desc = listing.get("description", "") or ""
        if len(desc) > 500:
            desc = desc[:500] + "..."

        parts.append(f"""--- Property {i} ---
Rightmove ID: {listing.get('rightmove_id')}
URL: {listing.get('url')}
Price: {listing.get('display_price', 'N/A')}
Address: {listing.get('display_address', 'N/A')}
Bedrooms: {listing.get('bedrooms', 'N/A')}
Bathrooms: {listing.get('bathrooms', 'N/A')}
Type: {listing.get('property_sub_type', 'N/A')}
Furnished: {listing.get('furnish_type', 'N/A')}
Key Features: {', '.join(features) if features else 'N/A'}
Description: {desc}
""")

    return "\n".join(parts)


def analyze_listings(listings):
    """Send listings to Claude for analysis and ranking."""
    if not listings:
        logger.warning("No listings to analyze")
        return None

    if not Config.ANTHROPIC_API_KEY:
        logger.error("ANTHROPIC_API_KEY not configured")
        return None

    formatted = format_listings_for_claude(listings)
    user_prompt = f"Here are {len(listings)} rental properties found today. Please analyze and rank the top 5:\n\n{formatted}"

    try:
        response = _get_client().messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=2000,
            system=ANALYSIS_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )
    except Exception as e:
        logger.error(f"Claude API call failed: {e}")
        return None

    raw_text = response.content[0].text
    tokens_used = response.usage.input_tokens + response.usage.output_tokens

    # Parse JSON from response
    parsed = _parse_json_response(raw_text)
    if not parsed:
        logger.warning("Failed to parse Claude response as JSON, returning raw")
        parsed = {"rankings": [], "summary": raw_text}

    return {
        "model": response.model,
        "prompt": user_prompt,
        "raw_response": raw_text,
        "rankings": parsed.get("rankings", []),
        "summary": parsed.get("summary", ""),
        "tokens_used": tokens_used,
    }


def _parse_json_response(text):
    """Try to parse JSON from Claude's response, handling markdown code blocks."""
    # Direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try extracting from markdown code blocks
    import re
    json_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass

    # Try finding a JSON object in the text
    brace_start = text.find('{')
    brace_end = text.rfind('}')
    if brace_start != -1 and brace_end != -1:
        try:
            return json.loads(text[brace_start:brace_end + 1])
        except json.JSONDecodeError:
            pass

    return None
