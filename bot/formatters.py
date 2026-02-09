"""Format data for Telegram messages"""
import json
from typing import List, Dict


def format_listings_for_telegram(listings: List[Dict], query_context: Dict = None, detailed: bool = False) -> str:
    """Format listings for Telegram message"""

    if not listings:
        return "No listings found."

    output = []

    # Header
    count = len(listings)
    if query_context:
        price = query_context.get("price_max")
        beds = query_context.get("bedrooms")
        header = f"Found {count} propert{'y' if count == 1 else 'ies'}"
        if price:
            header += f" under £{price}"
        if beds:
            header += f" with {beds} bedroom{'s' if beds > 1 else ''}"
        output.append(f"<b>{header}</b>\n")
    else:
        output.append(f"<b>Showing {count} listing{'s' if count > 1 else ''}</b>\n")

    # Format each listing
    for i, listing in enumerate(listings, 1):
        price = listing.get("display_price", "N/A")
        address = listing.get("display_address", "Unknown")
        beds = listing.get("bedrooms", "?")
        url = listing.get("url", "")

        # Basic info
        output.append(f"\n{i}. <b>{price}</b> - {beds} bed")
        output.append(f"   📍 {address}")

        # Additional details if detailed view
        if detailed:
            furnish = listing.get("furnish_type", "")
            if furnish:
                output.append(f"   🛋 {furnish}")

            features = listing.get("key_features")
            if features:
                try:
                    features_list = json.loads(features) if isinstance(features, str) else features
                    if features_list:
                        # Show more features in detailed view
                        features_text = ', '.join(features_list[:5])
                        output.append(f"   ✨ {features_text}")
                except:
                    pass

            # Add description snippet
            description = listing.get("description", "")
            if description:
                # Remove HTML tags and clean up
                import re
                desc_clean = re.sub(r'<[^>]+>', ' ', description)  # Remove HTML tags
                desc_clean = re.sub(r'\s+', ' ', desc_clean)  # Normalize whitespace
                desc_clean = desc_clean.strip()

                # Take first 150 characters and add ellipsis
                desc_snippet = desc_clean[:150].strip()
                if len(desc_clean) > 150:
                    desc_snippet += "..."
                output.append(f"   📝 {desc_snippet}")

        # Link
        if url:
            output.append(f"   🔗 <a href='{url}'>View on Rightmove</a>")

    return "\n".join(output)


def format_analysis_summary(analysis: Dict, listings_map: Dict = None) -> str:
    """Format Claude analysis for Telegram

    Args:
        analysis: Analysis data from database
        listings_map: Optional dict of {rightmove_id: full_listing_data} to enrich with URLs
    """

    if not analysis:
        return "No analysis available."

    output = ["<b>🤖 Claude's Analysis</b>\n"]

    # Extract ranked listings
    ranked = analysis.get("ranked_listings", [])
    raw_response = analysis.get("raw_response", "")

    if ranked:
        output.append(f"<b>Top {len(ranked)} Recommendations:</b>\n")

        for i, item in enumerate(ranked[:5], 1):
            rightmove_id = item.get("rightmove_id", "")
            address = item.get("address", "Unknown")
            reason = item.get("reason", item.get("reasoning", "Good match"))
            price = item.get("price", "")

            # Try to get URL from the item first, otherwise from listings_map
            url = item.get("url", "")
            if not url and listings_map and rightmove_id:
                listing = listings_map.get(str(rightmove_id))
                if listing:
                    url = listing.get("url", "")
                    if not price:
                        price = listing.get("display_price", "")

            output.append(f"\n{i}. <b>{price or 'Price TBC'}</b> - {address}")
            output.append(f"   💭 {reason}")
            if url:
                output.append(f"   🔗 <a href='{url}'>View on Rightmove</a>")

    # Add summary if available
    if raw_response and "summary" in raw_response.lower():
        output.append(f"\n<b>Summary:</b>")
        # Extract summary portion (simple heuristic)
        lines = raw_response.split("\n")
        for line in lines:
            if line.strip() and not line.startswith("{"):
                output.append(line.strip())
                break

    output.append(f"\n<i>Generated: {analysis.get('created_at', 'Unknown')}</i>")

    return "\n".join(output)
