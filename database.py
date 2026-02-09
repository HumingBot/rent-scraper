import sqlite3
import json
from datetime import datetime, timezone
from contextlib import contextmanager
from config import Config, DEFAULT_SEARCH_SETTINGS

DB_PATH = Config.DATABASE_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scrape_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL DEFAULT 'running',
    total_found INTEGER DEFAULT 0,
    new_listings INTEGER DEFAULT 0,
    error_message TEXT,
    search_params TEXT
);

CREATE TABLE IF NOT EXISTS listings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rightmove_id TEXT UNIQUE NOT NULL,
    url TEXT NOT NULL,
    display_price TEXT,
    price_numeric INTEGER,
    display_address TEXT,
    bedrooms INTEGER,
    bathrooms INTEGER,
    size_sq_ft TEXT,
    furnish_type TEXT,
    property_sub_type TEXT,
    key_features TEXT,
    description TEXT,
    latitude REAL,
    longitude REAL,
    agent_name TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    let_agreed INTEGER DEFAULT 0,
    image_url TEXT
);

CREATE TABLE IF NOT EXISTS run_listings (
    run_id INTEGER NOT NULL,
    listing_id INTEGER NOT NULL,
    is_new INTEGER DEFAULT 0,
    PRIMARY KEY (run_id, listing_id),
    FOREIGN KEY (run_id) REFERENCES scrape_runs(id),
    FOREIGN KEY (listing_id) REFERENCES listings(id)
);

CREATE TABLE IF NOT EXISTS analyses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL UNIQUE,
    model_used TEXT,
    prompt_sent TEXT,
    raw_response TEXT,
    ranked_listings TEXT,
    created_at TEXT NOT NULL,
    tokens_used INTEGER,
    FOREIGN KEY (run_id) REFERENCES scrape_runs(id)
);

CREATE INDEX IF NOT EXISTS idx_listings_rightmove_id ON listings(rightmove_id);
CREATE INDEX IF NOT EXISTS idx_listings_price ON listings(price_numeric);
CREATE INDEX IF NOT EXISTS idx_listings_first_seen ON listings(first_seen_at);
CREATE INDEX IF NOT EXISTS idx_run_listings_run ON run_listings(run_id);

CREATE TABLE IF NOT EXISTS conversation_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER NOT NULL,
    role TEXT NOT NULL,
    message TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    analysis_id INTEGER,
    FOREIGN KEY (analysis_id) REFERENCES analyses(id)
);

CREATE TABLE IF NOT EXISTS user_context (
    telegram_id INTEGER PRIMARY KEY,
    last_active_at TEXT NOT NULL,
    current_focus TEXT,
    focus_data TEXT,
    preferences TEXT
);

CREATE TABLE IF NOT EXISTS user_listing_views (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER NOT NULL,
    listing_id INTEGER NOT NULL,
    position INTEGER NOT NULL,
    shown_at TEXT NOT NULL,
    conversation_context TEXT,
    FOREIGN KEY (listing_id) REFERENCES listings(id)
);

CREATE INDEX IF NOT EXISTS idx_conversation_telegram ON conversation_history(telegram_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_user_listing_views ON user_listing_views(telegram_id, shown_at);
"""


def _now():
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with get_db() as conn:
        conn.executescript(SCHEMA)
        # Seed default settings if empty
        count = conn.execute("SELECT COUNT(*) FROM settings").fetchone()[0]
        if count == 0:
            now = _now()
            for key, value in DEFAULT_SEARCH_SETTINGS.items():
                conn.execute(
                    "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
                    (key, json.dumps(value), now),
                )


def get_setting(key):
    with get_db() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        if row:
            return json.loads(row["value"])
        return None


def get_all_settings():
    with get_db() as conn:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
        return {row["key"]: json.loads(row["value"]) for row in rows}


def update_setting(key, value):
    with get_db() as conn:
        conn.execute(
            "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
            (key, json.dumps(value), _now()),
        )


def update_settings(settings_dict):
    with get_db() as conn:
        now = _now()
        for key, value in settings_dict.items():
            conn.execute(
                "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
                (key, json.dumps(value), now),
            )


def create_scrape_run(search_params):
    with get_db() as conn:
        cursor = conn.execute(
            "INSERT INTO scrape_runs (started_at, status, search_params) VALUES (?, 'running', ?)",
            (_now(), json.dumps(search_params)),
        )
        return cursor.lastrowid


def complete_scrape_run(run_id, status, total, new, error=None):
    with get_db() as conn:
        conn.execute(
            "UPDATE scrape_runs SET completed_at = ?, status = ?, total_found = ?, new_listings = ?, error_message = ? WHERE id = ?",
            (_now(), status, total, new, error, run_id),
        )


def upsert_listing(data):
    now = _now()
    with get_db() as conn:
        # Check if exists
        existing = conn.execute(
            "SELECT id FROM listings WHERE rightmove_id = ?", (data["rightmove_id"],)
        ).fetchone()

        if existing:
            conn.execute(
                """UPDATE listings SET
                    url = ?, display_price = ?, price_numeric = ?, display_address = ?,
                    bedrooms = ?, bathrooms = ?, size_sq_ft = ?, furnish_type = ?,
                    property_sub_type = ?, key_features = ?, description = ?,
                    latitude = ?, longitude = ?, agent_name = ?, last_seen_at = ?,
                    let_agreed = ?, image_url = ?
                WHERE rightmove_id = ?""",
                (
                    data.get("url"), data.get("display_price"), data.get("price_numeric"),
                    data.get("display_address"), data.get("bedrooms"), data.get("bathrooms"),
                    data.get("size_sq_ft"), data.get("furnish_type"), data.get("property_sub_type"),
                    data.get("key_features"), data.get("description"),
                    data.get("latitude"), data.get("longitude"), data.get("agent_name"),
                    now, data.get("let_agreed", 0), data.get("image_url"),
                    data["rightmove_id"],
                ),
            )
            return existing["id"], False
        else:
            cursor = conn.execute(
                """INSERT INTO listings (
                    rightmove_id, url, display_price, price_numeric, display_address,
                    bedrooms, bathrooms, size_sq_ft, furnish_type, property_sub_type,
                    key_features, description, latitude, longitude, agent_name,
                    first_seen_at, last_seen_at, let_agreed, image_url
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    data["rightmove_id"], data.get("url"), data.get("display_price"),
                    data.get("price_numeric"), data.get("display_address"),
                    data.get("bedrooms"), data.get("bathrooms"), data.get("size_sq_ft"),
                    data.get("furnish_type"), data.get("property_sub_type"),
                    data.get("key_features"), data.get("description"),
                    data.get("latitude"), data.get("longitude"), data.get("agent_name"),
                    now, now, data.get("let_agreed", 0), data.get("image_url"),
                ),
            )
            return cursor.lastrowid, True


def link_run_listing(run_id, listing_id, is_new):
    with get_db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO run_listings (run_id, listing_id, is_new) VALUES (?, ?, ?)",
            (run_id, listing_id, 1 if is_new else 0),
        )


def get_listings(filters=None, sort="first_seen_at", order="DESC", limit=100, offset=0):
    allowed_sorts = {"price_numeric", "first_seen_at", "display_address", "bedrooms", "last_seen_at"}
    if sort not in allowed_sorts:
        sort = "first_seen_at"
    if order.upper() not in ("ASC", "DESC"):
        order = "DESC"

    where_clauses = []
    params = []
    if filters:
        if filters.get("min_price") is not None:
            where_clauses.append("price_numeric >= ?")
            params.append(filters["min_price"])
        if filters.get("max_price") is not None:
            where_clauses.append("price_numeric <= ?")
            params.append(filters["max_price"])
        if filters.get("bedrooms") is not None:
            where_clauses.append("bedrooms = ?")
            params.append(filters["bedrooms"])

    where_sql = ""
    if where_clauses:
        where_sql = "WHERE " + " AND ".join(where_clauses)

    query = f"SELECT * FROM listings {where_sql} ORDER BY {sort} {order} LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    with get_db() as conn:
        rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]


def get_listings_count(filters=None):
    where_clauses = []
    params = []
    if filters:
        if filters.get("min_price") is not None:
            where_clauses.append("price_numeric >= ?")
            params.append(filters["min_price"])
        if filters.get("max_price") is not None:
            where_clauses.append("price_numeric <= ?")
            params.append(filters["max_price"])
        if filters.get("bedrooms") is not None:
            where_clauses.append("bedrooms = ?")
            params.append(filters["bedrooms"])

    where_sql = ""
    if where_clauses:
        where_sql = "WHERE " + " AND ".join(where_clauses)

    with get_db() as conn:
        row = conn.execute(f"SELECT COUNT(*) as cnt FROM listings {where_sql}", params).fetchone()
        return row["cnt"]


def get_run_listings(run_id):
    with get_db() as conn:
        rows = conn.execute(
            """SELECT l.*, rl.is_new FROM listings l
               JOIN run_listings rl ON l.id = rl.listing_id
               WHERE rl.run_id = ?
               ORDER BY l.price_numeric ASC""",
            (run_id,),
        ).fetchall()
        return [dict(row) for row in rows]


def get_runs(limit=20):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM scrape_runs ORDER BY started_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(row) for row in rows]


def save_analysis(run_id, model, prompt, response, ranked, tokens):
    with get_db() as conn:
        conn.execute(
            """INSERT INTO analyses (run_id, model_used, prompt_sent, raw_response, ranked_listings, created_at, tokens_used)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (run_id, model, prompt, response, json.dumps(ranked), _now(), tokens),
        )


def get_analysis(run_id):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM analyses WHERE run_id = ?", (run_id,)).fetchone()
        if row:
            result = dict(row)
            result["ranked_listings"] = json.loads(result["ranked_listings"]) if result["ranked_listings"] else []
            return result
        return None


def get_latest_analysis():
    with get_db() as conn:
        row = conn.execute("SELECT * FROM analyses ORDER BY created_at DESC LIMIT 1").fetchone()
        if row:
            result = dict(row)
            result["ranked_listings"] = json.loads(result["ranked_listings"]) if result["ranked_listings"] else []
            return result
        return None


# Bot-related database functions

def save_conversation_turn(telegram_id, role, message, analysis_id=None):
    """Save a conversation turn for context"""
    with get_db() as conn:
        conn.execute(
            "INSERT INTO conversation_history (telegram_id, role, message, timestamp, analysis_id) VALUES (?, ?, ?, ?, ?)",
            (telegram_id, role, message, _now(), analysis_id)
        )


def get_conversation_history(telegram_id, limit=10):
    """Get recent conversation history"""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM conversation_history WHERE telegram_id = ? ORDER BY timestamp DESC LIMIT ?",
            (telegram_id, limit)
        ).fetchall()
        return [dict(row) for row in reversed(rows)]  # Return in chronological order


def get_user_context(telegram_id):
    """Get current user context and preferences"""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM user_context WHERE telegram_id = ?",
            (telegram_id,)
        ).fetchone()
        if row:
            result = dict(row)
            if result.get("preferences"):
                result["preferences"] = json.loads(result["preferences"])
            if result.get("focus_data"):
                result["focus_data"] = json.loads(result["focus_data"])
            return result
        return None


def update_user_context(telegram_id, focus, focus_data):
    """Update what the user is currently discussing"""
    with get_db() as conn:
        conn.execute(
            """INSERT INTO user_context (telegram_id, last_active_at, current_focus, focus_data)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(telegram_id) DO UPDATE SET
                   last_active_at = excluded.last_active_at,
                   current_focus = excluded.current_focus,
                   focus_data = excluded.focus_data""",
            (telegram_id, _now(), focus, json.dumps(focus_data))
        )


def mark_listing_shown(telegram_id, listing_id, position, context):
    """Track that a listing was shown to user with its reference number"""
    with get_db() as conn:
        conn.execute(
            "INSERT INTO user_listing_views (telegram_id, listing_id, position, shown_at, conversation_context) VALUES (?, ?, ?, ?, ?)",
            (telegram_id, listing_id, position, _now(), context)
        )


def get_recently_shown_listings(telegram_id, hours=24):
    """Get listings shown to user recently for follow-ups (today only by default)"""
    with get_db() as conn:
        rows = conn.execute(
            """SELECT ulv.*, l.display_address, l.price_numeric, l.url
               FROM user_listing_views ulv
               JOIN listings l ON ulv.listing_id = l.id
               WHERE ulv.telegram_id = ?
               AND datetime(ulv.shown_at) >= datetime('now', '-' || ? || ' hours')
               ORDER BY ulv.shown_at DESC""",
            (telegram_id, hours)
        ).fetchall()
        return [dict(row) for row in rows]


def get_listing_by_reference(telegram_id, position, hours=24):
    """Get a specific listing by its reference number (e.g., 'the second one' = position 2)"""
    with get_db() as conn:
        row = conn.execute(
            """SELECT ulv.*, l.*
               FROM user_listing_views ulv
               JOIN listings l ON ulv.listing_id = l.id
               WHERE ulv.telegram_id = ?
               AND ulv.position = ?
               AND datetime(ulv.shown_at) >= datetime('now', '-' || ? || ' hours')
               ORDER BY ulv.shown_at DESC
               LIMIT 1""",
            (telegram_id, position, hours)
        ).fetchone()
        return dict(row) if row else None


def clear_old_conversation_history(telegram_id, days=1):
    """Clear conversation history older than N days (default: daily reset)"""
    with get_db() as conn:
        conn.execute(
            """DELETE FROM conversation_history
               WHERE telegram_id = ?
               AND datetime(timestamp) < datetime('now', '-' || ? || ' days')""",
            (telegram_id, days)
        )
        conn.execute(
            """DELETE FROM user_listing_views
               WHERE telegram_id = ?
               AND datetime(shown_at) < datetime('now', '-' || ? || ' days')""",
            (telegram_id, days)
        )
