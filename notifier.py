import logging
import requests
from config import Config

logger = logging.getLogger(__name__)

TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/sendMessage"


def send_telegram_message(text, parse_mode="HTML"):
    """Send a message to the configured Telegram chat."""
    token = Config.TELEGRAM_BOT_TOKEN
    chat_id = Config.TELEGRAM_CHAT_ID

    if not token or not chat_id:
        logger.warning("Telegram not configured (missing token or chat_id), skipping notification")
        return False

    url = TELEGRAM_API_URL.format(token=token)
    chunks = split_message(text, max_len=4096)

    for chunk in chunks:
        try:
            resp = requests.post(
                url,
                json={"chat_id": chat_id, "text": chunk, "parse_mode": parse_mode},
                timeout=10,
            )
            if resp.status_code != 200:
                logger.error(f"Telegram send failed ({resp.status_code}): {resp.text}")
                return False
        except requests.RequestException as e:
            logger.error(f"Telegram request error: {e}")
            return False

    logger.info(f"Telegram message sent ({len(chunks)} chunk(s))")
    return True


def split_message(text, max_len=4096):
    """Split a long message at newline boundaries."""
    if len(text) <= max_len:
        return [text]

    chunks = []
    while text:
        if len(text) <= max_len:
            chunks.append(text)
            break

        # Find last newline before max_len
        split_at = text.rfind('\n', 0, max_len)
        if split_at == -1:
            split_at = max_len

        chunks.append(text[:split_at])
        text = text[split_at:].lstrip('\n')

    return chunks


def format_analysis_message(analysis, listings):
    """Format Claude's analysis into a Telegram-friendly HTML message."""
    rankings = analysis.get("rankings", [])
    summary = analysis.get("summary", "")
    total = len(listings) if listings else 0

    lines = [
        "<b>🏠 Daily Rental Report</b>",
        f"<i>{total} listings analysed</i>",
        "",
    ]

    # Build a lookup of listings by rightmove_id
    listings_map = {}
    if listings:
        for l in listings:
            rid = l.get("rightmove_id", str(l.get("id", "")))
            listings_map[str(rid)] = l

    for r in rankings:
        rank = r.get("rank", "?")
        rid = str(r.get("rightmove_id", ""))
        reasoning = r.get("reasoning", "")
        address = r.get("address", "")
        price = r.get("price", "")

        # Try to get address/price from listings if not in ranking
        if rid in listings_map:
            listing = listings_map[rid]
            if not address:
                address = listing.get("display_address", "Unknown")
            if not price:
                price = listing.get("display_price", "N/A")

        url = f"https://www.rightmove.co.uk/properties/{rid}"

        lines.append(f"<b>#{rank}: {price} - {address}</b>")
        lines.append(f"{reasoning}")
        lines.append(f"<a href=\"{url}\">View on Rightmove</a>")
        lines.append("")

    if summary:
        lines.append(f"<b>Summary:</b> {summary}")

    return "\n".join(lines)
