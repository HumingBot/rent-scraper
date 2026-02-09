import re
import json
import time
import random
import logging
import requests

logger = logging.getLogger(__name__)

SEARCH_HTML_URL = "https://www.rightmove.co.uk/property-to-rent/find.html"
PROPERTY_URL_TEMPLATE = "https://www.rightmove.co.uk/properties/{}"

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
}

SESSION = requests.Session()
SESSION.headers.update(DEFAULT_HEADERS)


def build_search_url(settings):
    params = {
        "searchLocation": settings.get("location_display_name", "London"),
        "useLocationIdentifier": "true",
        "locationIdentifier": settings.get("location_identifier", "REGION%5E87490"),
        "radius": settings.get("radius", 3.0),
        "minPrice": settings.get("min_price", 1300),
        "maxPrice": settings.get("max_price", 1750),
        "minBedrooms": settings.get("min_bedrooms", 1),
        "maxBedrooms": settings.get("max_bedrooms", 1),
        "propertyTypes": settings.get("property_type", "flat"),
        "maxDaysSinceAdded": settings.get("max_days_since_added", 1),
    }
    if settings.get("include_let_agreed", True):
        params["_includeLetAgreed"] = "on"

    query = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{SEARCH_HTML_URL}?{query}"


def search_properties(settings):
    """Search Rightmove and return list of property ID strings."""
    url = build_search_url(settings)
    logger.info(f"Searching: {url}")

    all_ids = set()
    index = 0

    while True:
        page_url = f"{url}&index={index}" if index > 0 else url
        try:
            resp = SESSION.get(page_url, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as e:
            logger.error(f"Search request failed at index {index}: {e}")
            break

        html = resp.text

        # Extract property IDs from URLs in the HTML
        ids = re.findall(r'/properties/(\d+)', html)
        unique_ids = set(ids)

        if not unique_ids:
            break

        new_ids = unique_ids - all_ids
        if not new_ids:
            break  # No new results on this page

        all_ids.update(unique_ids)
        logger.info(f"Page index={index}: found {len(unique_ids)} IDs ({len(new_ids)} new)")

        # Check if there's a next page
        if 'pagination-direction--next' not in html:
            break

        index += 24  # Rightmove shows 24 per page
        time.sleep(random.uniform(1.0, 2.0))

    logger.info(f"Total unique property IDs found: {len(all_ids)}")
    return list(all_ids)


def parse_price(price_str):
    """Extract numeric monthly price from strings like '1,500 pcm' or '£1,500'."""
    if not price_str:
        return None
    numbers = re.findall(r'[\d,]+', price_str)
    if numbers:
        try:
            return int(numbers[0].replace(',', ''))
        except ValueError:
            return None
    return None


def fetch_property_details(rightmove_id):
    """Fetch a single property page and extract details from PAGE_MODEL."""
    url = PROPERTY_URL_TEMPLATE.format(rightmove_id)

    try:
        resp = SESSION.get(url, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.warning(f"Failed to fetch property {rightmove_id}: {e}")
        return None

    html = resp.text

    # Try to extract PAGE_MODEL JSON
    page_model_match = re.search(r'PAGE_MODEL\s*=\s*({.*?})\s*</script>', html, re.DOTALL)

    if page_model_match:
        try:
            page_model = json.loads(page_model_match.group(1))
            return _extract_from_page_model(rightmove_id, url, page_model)
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse PAGE_MODEL JSON for {rightmove_id}")

    # Fallback: extract from HTML using regex (matching n8n workflow approach)
    return _extract_from_html(rightmove_id, url, html)


def _extract_from_page_model(rightmove_id, url, page_model):
    """Extract property details from the parsed PAGE_MODEL JSON."""
    prop = page_model.get("propertyData", {})

    prices = prop.get("prices", {})
    price_str = prices.get("primaryPrice", "")

    address = prop.get("address", {})
    location = prop.get("location", {})
    lettings = prop.get("lettings", {})
    customer = prop.get("customer", {})
    images = prop.get("images", [])
    sizings = prop.get("sizings", [])
    text = prop.get("text", {})

    return {
        "rightmove_id": rightmove_id,
        "url": url,
        "display_price": price_str,
        "price_numeric": parse_price(price_str),
        "display_address": address.get("displayAddress", ""),
        "bedrooms": prop.get("bedrooms"),
        "bathrooms": prop.get("bathrooms"),
        "size_sq_ft": sizings[0].get("minimumSize", "") if sizings else None,
        "furnish_type": lettings.get("furnishType", ""),
        "property_sub_type": prop.get("propertySubType", ""),
        "key_features": json.dumps(prop.get("keyFeatures", [])),
        "description": text.get("description", ""),
        "latitude": location.get("latitude"),
        "longitude": location.get("longitude"),
        "agent_name": customer.get("branchDisplayName", ""),
        "let_agreed": 1 if "LET AGREED" in str(prop.get("tags", [])).upper() else 0,
        "image_url": images[0].get("url", "") if images else None,
    }


def _extract_from_html(rightmove_id, url, html):
    """Fallback: extract property details using regex on raw HTML (mirrors n8n Code nodes)."""
    def match_first(pattern, text, group=1):
        m = re.search(pattern, text)
        return m.group(group) if m else None

    def unescape_unicode(s):
        if not s:
            return s
        return s.encode().decode('unicode_escape', errors='ignore')

    price = match_first(r'"displayPrice":"([^"]+)"', html) or match_first(r'£([\d,]+)\s*pcm', html)
    address = unescape_unicode(match_first(r'"displayAddress":"([^"]+)"', html))

    # Key features from HTML <li> tags
    key_features = []
    features_section = re.search(r'"keyFeatures">(.+?)</ul>', html, re.DOTALL)
    if features_section:
        key_features = re.findall(r'<li[^>]*>([^<]+)</li>', features_section.group(1))

    description = unescape_unicode(
        match_first(r'"text":\{"description":"([^"]+)"', html)
        or match_first(r'"summary":"([^"]+)"', html)
    )

    return {
        "rightmove_id": rightmove_id,
        "url": url,
        "display_price": price,
        "price_numeric": parse_price(price),
        "display_address": address,
        "bedrooms": _safe_int(match_first(r'"bedrooms":(\d+)', html)),
        "bathrooms": _safe_int(match_first(r'"bathrooms":(\d+)', html)),
        "size_sq_ft": match_first(r'"size":(\d+)', html),
        "furnish_type": match_first(r'"furnishType":"([^"]+)"', html),
        "property_sub_type": match_first(r'"propertySubType":"([^"]+)"', html),
        "key_features": json.dumps(key_features),
        "description": description,
        "latitude": _safe_float(match_first(r'"latitude":([\d.]+)', html)),
        "longitude": _safe_float(match_first(r'"longitude":([-\d.]+)', html)),
        "agent_name": match_first(r'"branchDisplayName":"([^"]+)"', html),
        "let_agreed": 1 if "Let Agreed" in html else 0,
        "image_url": match_first(r'"srcUrl":"(https://[^"]+\.jpg)"', html),
    }


def _safe_int(val):
    try:
        return int(val) if val else None
    except (ValueError, TypeError):
        return None


def _safe_float(val):
    try:
        return float(val) if val else None
    except (ValueError, TypeError):
        return None


def run_scrape(settings):
    """Run the full scrape pipeline: search + fetch each property."""
    property_ids = search_properties(settings)
    properties = []
    errors = 0

    for i, pid in enumerate(property_ids):
        logger.info(f"Fetching property {i+1}/{len(property_ids)}: {pid}")
        try:
            details = fetch_property_details(pid)
            if details:
                properties.append(details)
            else:
                errors += 1
        except Exception as e:
            logger.error(f"Error fetching property {pid}: {e}")
            errors += 1

        # Rate limiting
        if i < len(property_ids) - 1:
            time.sleep(random.uniform(1.0, 2.5))

    logger.info(f"Scrape complete: {len(properties)} properties, {errors} errors")
    return {"properties": properties, "total_found": len(properties), "errors": errors}
