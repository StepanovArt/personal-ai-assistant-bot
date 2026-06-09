"""
Database layer for the personal AI assistant.

Stores:
- Users and their interests
- History of shown news articles (to avoid duplicates across runs)
"""

import os
import sqlite3
import json
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = os.getenv("DB_PATH", str(PROJECT_ROOT / "personal_ai.db"))


# ============================================================
# CONNECTION CONTEXT MANAGER
# ============================================================
@contextmanager
def get_db():
    """
    Context manager for database connections.

    Automatically:
    - Opens a connection
    - Enables foreign keys
    - Commits on success
    - Rolls back on error
    - Closes the connection in all cases

    Usage:
        with get_db() as conn:
            conn.execute("INSERT ...")
            # commit happens automatically
    """
    conn = sqlite3.connect(DB_PATH)
    # row_factory allows column access by name: row["name"] instead of row[1]
    conn.row_factory = sqlite3.Row
    # Enable foreign key checks (disabled by default in SQLite)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ============================================================
# SCHEMA INITIALISATION
# ============================================================
def init_db() -> None:
    """Creates tables and indexes if they don't exist. Safe to run multiple times."""
    with get_db() as conn:
        # --- Users table ---
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id  INTEGER UNIQUE NOT NULL,
                interests    TEXT    NOT NULL DEFAULT '[]',
                created_at   TEXT    NOT NULL DEFAULT (datetime('now')),
                updated_at   TEXT    NOT NULL DEFAULT (datetime('now'))
            )
        """)

        # --- Shown news table ---
        # ON DELETE CASCADE: deleting a user also deletes their news history
        conn.execute("""
            CREATE TABLE IF NOT EXISTS shown_news (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id   INTEGER NOT NULL,
                url       TEXT    NOT NULL,
                title     TEXT,
                shown_at  TEXT    NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

        # --- Index for fast "was this article shown?" lookups ---
        # Composite index covers WHERE user_id = ? AND url = ?
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_shown_news_user_url
            ON shown_news(user_id, url)
        """)

        # --- Index for user lookup by telegram_id ---
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_users_telegram
            ON users(telegram_id)
        """)

        # --- Expenses table ---
        conn.execute("""
            CREATE TABLE IF NOT EXISTS expenses (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                amount      REAL    NOT NULL,
                currency    TEXT    NOT NULL DEFAULT 'AED',
                category    TEXT    NOT NULL,
                description TEXT,
                created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_expenses_user_created
            ON expenses(user_id, created_at)
        """)

        # --- Migration: add new columns to users (safe for existing DBs) ---
        for col, definition in [
            ("gmail_user",         "TEXT"),
            ("gmail_app_password", "TEXT"),
            ("is_onboarded",       "INTEGER NOT NULL DEFAULT 0"),
            ("oauth_token",        "TEXT"),
        ]:
            try:
                conn.execute(f"ALTER TABLE users ADD COLUMN {col} {definition}")
            except Exception:
                pass  # column already exists


# ============================================================
# USER OPERATIONS
# ============================================================
def get_user(telegram_id: int) -> Optional[dict]:
    """Returns user by telegram_id or None if not found. Interests are parsed from JSON."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE telegram_id = ?",
            (telegram_id,)
        ).fetchone()

        if row is None:
            return None

        # Convert sqlite3.Row to plain dict and parse JSON interests
        user = dict(row)
        user["interests"] = json.loads(user["interests"])
        return user


def add_user(telegram_id: int, interests: list[str]) -> int:
    """Creates a new user and returns their internal id. Raises IntegrityError if telegram_id already exists."""
    with get_db() as conn:
        cursor = conn.execute(
            "INSERT INTO users (telegram_id, interests) VALUES (?, ?)",
            (telegram_id, json.dumps(interests, ensure_ascii=False))
        )
        return cursor.lastrowid


def get_or_create_user(telegram_id: int, interests: list[str]) -> dict:
    """Returns existing user or creates a new one. Safe entry point for all Telegram interactions."""
    existing = get_user(telegram_id)
    if existing is not None:
        return existing

    add_user(telegram_id, interests)
    return get_user(telegram_id)


def update_user_interests(telegram_id: int, new_interests: list[str]) -> bool:
    """Updates user interests. Returns True if user was found and updated, False otherwise."""
    with get_db() as conn:
        cursor = conn.execute(
            """
            UPDATE users
            SET interests = ?, updated_at = datetime('now')
            WHERE telegram_id = ?
            """,
            (json.dumps(new_interests, ensure_ascii=False), telegram_id)
        )
        # rowcount = number of rows affected; 0 means user not found
        return cursor.rowcount > 0


# ============================================================
# SHOWN NEWS OPERATIONS
# ============================================================
def is_news_shown(user_id: int, url: str) -> bool:
    """Returns True if this article has already been shown to the user."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT 1 FROM shown_news WHERE user_id = ? AND url = ? LIMIT 1",
            (user_id, url)
        ).fetchone()
        return row is not None


def mark_news_shown(user_id: int, url: str, title: Optional[str] = None) -> None:
    """Marks an article as shown to the user. title is optional, useful for debugging."""
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO shown_news (user_id, url, title)
            VALUES (?, ?, ?)
            """,
            (user_id, url, title)
        )


def filter_unseen_urls(user_id: int, urls: list[str]) -> set[str]:
    """
    Returns the subset of URLs not yet shown to the user.

    Uses a single IN query instead of N individual lookups — critical for performance at 50+ articles.
    """
    if not urls:
        return set()

    with get_db() as conn:
        # Dynamically build placeholders: ?, ?, ?, ...
        placeholders = ",".join("?" * len(urls))
        query = f"""
            SELECT url FROM shown_news
            WHERE user_id = ? AND url IN ({placeholders})
        """
        seen_rows = conn.execute(query, (user_id, *urls)).fetchall()
        seen_urls = {row["url"] for row in seen_rows}

        return set(urls) - seen_urls


def cleanup_old_shown_news(days: int = 30) -> int:
    """Deletes shown_news records older than N days. Run daily or weekly to prevent unbounded growth."""
    with get_db() as conn:
        cursor = conn.execute(
            """
            DELETE FROM shown_news
            WHERE shown_at < datetime('now', ?)
            """,
            (f'-{days} days',)
        )
        return cursor.rowcount


# ============================================================
# EXPENSE OPERATIONS
# ============================================================
def add_expense(
    user_id: int, amount: float, currency: str, category: str, description: str
) -> int:
    """Saves an expense and returns its id."""
    with get_db() as conn:
        cursor = conn.execute(
            """
            INSERT INTO expenses (user_id, amount, currency, category, description)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, amount, currency, category, description),
        )
        return cursor.lastrowid


def get_expenses(user_id: int, days: int = 30) -> list[dict]:
    """Returns the user's expenses for the last N days."""
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT * FROM expenses
            WHERE user_id = ? AND created_at >= datetime('now', ?)
            ORDER BY created_at DESC
            """,
            (user_id, f"-{days} days"),
        ).fetchall()
        return [dict(r) for r in rows]


def get_total_by_category(user_id: int, days: int = 30) -> list[dict]:
    """Returns total spending per category for the last N days, ordered descending."""
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT category, SUM(amount) AS total, currency
            FROM expenses
            WHERE user_id = ? AND created_at >= datetime('now', ?)
            GROUP BY category, currency
            ORDER BY total DESC
            """,
            (user_id, f"-{days} days"),
        ).fetchall()
        return [dict(r) for r in rows]


# ============================================================
# ONBOARDING
# ============================================================

def is_user_onboarded(telegram_id: int) -> bool:
    """Returns True if the user has completed onboarding."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT is_onboarded FROM users WHERE telegram_id = ?",
            (telegram_id,),
        ).fetchone()
        return bool(row and row["is_onboarded"])


def update_user_email_credentials(
    telegram_id: int, gmail_user: str, gmail_app_password: str
) -> None:
    """Saves Gmail credentials for a user."""
    with get_db() as conn:
        conn.execute(
            """
            UPDATE users
            SET gmail_user = ?, gmail_app_password = ?, updated_at = datetime('now')
            WHERE telegram_id = ?
            """,
            (gmail_user, gmail_app_password, telegram_id),
        )


def complete_onboarding(telegram_id: int) -> None:
    """Marks onboarding as completed for the user."""
    with get_db() as conn:
        conn.execute(
            "UPDATE users SET is_onboarded = 1, updated_at = datetime('now') WHERE telegram_id = ?",
            (telegram_id,),
        )


def get_user_email_credentials(telegram_id: int) -> tuple[str, str] | None:
    """Returns (gmail_user, gmail_app_password) or None if not set."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT gmail_user, gmail_app_password FROM users WHERE telegram_id = ?",
            (telegram_id,),
        ).fetchone()
        if row and row["gmail_user"] and row["gmail_app_password"]:
            return row["gmail_user"], row["gmail_app_password"]
        return None


def save_oauth_token(telegram_id: int, token_json: str, gmail_user: str = "") -> None:
    """Saves OAuth token JSON for a user, optionally updating gmail_user."""
    with get_db() as conn:
        if gmail_user:
            conn.execute(
                """UPDATE users SET oauth_token = ?, gmail_user = ?, updated_at = datetime('now')
                   WHERE telegram_id = ?""",
                (token_json, gmail_user, telegram_id),
            )
        else:
            conn.execute(
                "UPDATE users SET oauth_token = ?, updated_at = datetime('now') WHERE telegram_id = ?",
                (token_json, telegram_id),
            )


def get_oauth_token(telegram_id: int) -> str | None:
    """Returns OAuth token JSON string or None if not set."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT oauth_token FROM users WHERE telegram_id = ?",
            (telegram_id,),
        ).fetchone()
        if row and row["oauth_token"]:
            return row["oauth_token"]
        return None


# ============================================================
# SELF-CHECK ENTRY POINT
# ============================================================
if __name__ == "__main__":
    init_db()
    print("✅ DB initialised")

    user = get_or_create_user(telegram_id=12345, interests=["AI", "startups"])
    print(f"✅ User created/found: {user}")

    if not is_news_shown(user["id"], "https://example.com/test"):
        mark_news_shown(user["id"], "https://example.com/test", "Test Article")
        print("✅ Article marked as shown")

    print(f"✅ Duplicate check: {is_news_shown(user['id'], 'https://example.com/test')}")