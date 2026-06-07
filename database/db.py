"""
База данных для TrendWatcher Agent.

Хранит:
- Пользователей и их интересы
- Историю показанных новостей (чтобы не дублировать между запусками)
"""

import sqlite3
import json
from contextlib import contextmanager
from typing import Optional


# ============================================================
# КОНФИГУРАЦИЯ
# ============================================================
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = str(PROJECT_ROOT / "personal_ai.db")


# ============================================================
# CONTEXT MANAGER ДЛЯ СОЕДИНЕНИЙ
# ============================================================
@contextmanager
def get_db():
    """
    Контекстный менеджер для работы с БД.

    Автоматически:
    - Открывает соединение
    - Включает foreign keys
    - Коммитит транзакцию при успехе
    - Откатывает при ошибке
    - Закрывает соединение в любом случае

    Использование:
        with get_db() as conn:
            conn.execute("INSERT ...")
            # commit произойдёт автоматически
    """
    conn = sqlite3.connect(DB_PATH)
    # row_factory позволяет обращаться к колонкам по имени: row["name"] вместо row[1]
    conn.row_factory = sqlite3.Row
    # Включаем проверку foreign keys (по умолчанию ВЫКЛЮЧЕНО в SQLite)
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
# ИНИЦИАЛИЗАЦИЯ СХЕМЫ
# ============================================================
def init_db() -> None:
    """
    Создаёт таблицы и индексы, если их ещё нет.
    Безопасно запускать многократно.
    """
    with get_db() as conn:
        # --- Таблица пользователей ---
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id  INTEGER UNIQUE NOT NULL,
                interests    TEXT    NOT NULL DEFAULT '[]',
                created_at   TEXT    NOT NULL DEFAULT (datetime('now')),
                updated_at   TEXT    NOT NULL DEFAULT (datetime('now'))
            )
        """)

        # --- Таблица показанных новостей ---
        # ON DELETE CASCADE: если удалим юзера — его история сама удалится
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

        # --- Индекс для быстрой проверки "показывали ли эту новость" ---
        # Составной индекс работает для запросов WHERE user_id = ? AND url = ?
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_shown_news_user_url
            ON shown_news(user_id, url)
        """)

        # --- Индекс для поиска юзера по telegram_id ---
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_users_telegram
            ON users(telegram_id)
        """)

        # --- Таблица расходов ---
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

        # --- Миграция: новые колонки в users (безопасно для существующих БД) ---
        for col, definition in [
            ("gmail_user",         "TEXT"),
            ("gmail_app_password", "TEXT"),
            ("is_onboarded",       "INTEGER NOT NULL DEFAULT 0"),
        ]:
            try:
                conn.execute(f"ALTER TABLE users ADD COLUMN {col} {definition}")
            except Exception:
                pass  # колонка уже существует


# ============================================================
# ОПЕРАЦИИ С ПОЛЬЗОВАТЕЛЯМИ
# ============================================================
def get_user(telegram_id: int) -> Optional[dict]:
    """
    Возвращает пользователя по telegram_id или None, если не найден.
    Интересы автоматически парсятся из JSON в список.
    """
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE telegram_id = ?",
            (telegram_id,)
        ).fetchone()

        if row is None:
            return None

        # Превращаем sqlite3.Row в обычный dict + парсим JSON интересов
        user = dict(row)
        user["interests"] = json.loads(user["interests"])
        return user


def add_user(telegram_id: int, interests: list[str]) -> int:
    """
    Создаёт нового пользователя.
    Возвращает его внутренний id.

    Если пользователь с таким telegram_id уже существует — выбросит IntegrityError.
    Используй get_or_create_user, если не уверен.
    """
    with get_db() as conn:
        cursor = conn.execute(
            "INSERT INTO users (telegram_id, interests) VALUES (?, ?)",
            (telegram_id, json.dumps(interests, ensure_ascii=False))
        )
        return cursor.lastrowid


def get_or_create_user(telegram_id: int, interests: list[str]) -> dict:
    """
    Возвращает существующего юзера или создаёт нового.
    Атомарная операция — безопасна при гонках (например, два сообщения сразу).

    Это правильный способ "входа" в систему через Telegram.
    """
    existing = get_user(telegram_id)
    if existing is not None:
        return existing

    add_user(telegram_id, interests)
    # Возвращаем созданного юзера через get_user, чтобы получить полные поля
    return get_user(telegram_id)


def update_user_interests(telegram_id: int, new_interests: list[str]) -> bool:
    """
    Обновляет интересы пользователя.
    Возвращает True, если юзер найден и обновлён, False — если юзера нет.
    """
    with get_db() as conn:
        cursor = conn.execute(
            """
            UPDATE users
            SET interests = ?, updated_at = datetime('now')
            WHERE telegram_id = ?
            """,
            (json.dumps(new_interests, ensure_ascii=False), telegram_id)
        )
        # rowcount = сколько строк было затронуто. 0 = юзера не было.
        return cursor.rowcount > 0


# ============================================================
# ОПЕРАЦИИ С ПОКАЗАННЫМИ НОВОСТЯМИ
# ============================================================
def is_news_shown(user_id: int, url: str) -> bool:
    """Проверяет, показывали ли уже эту новость данному юзеру."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT 1 FROM shown_news WHERE user_id = ? AND url = ? LIMIT 1",
            (user_id, url)
        ).fetchone()
        return row is not None


def mark_news_shown(user_id: int, url: str, title: Optional[str] = None) -> None:
    """
    Помечает новость как показанную пользователю.
    title опционален — полезен для дебага и аналитики.
    """
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
    Возвращает множество URL'ов, которые ещё НЕ показывались юзеру.

    Это оптимизация: вместо N запросов к БД (по одному на каждый URL)
    делаем ОДИН запрос со списком. Критично для скорости при 50+ новостях.
    """
    if not urls:
        return set()

    with get_db() as conn:
        # Динамически генерируем placeholders: ?, ?, ?, ...
        placeholders = ",".join("?" * len(urls))
        query = f"""
            SELECT url FROM shown_news
            WHERE user_id = ? AND url IN ({placeholders})
        """
        # Параметры: сначала user_id, потом распакованный список urls
        seen_rows = conn.execute(query, (user_id, *urls)).fetchall()
        seen_urls = {row["url"] for row in seen_rows}

        # Возвращаем разность: все URL минус те, что уже видели
        return set(urls) - seen_urls


def cleanup_old_shown_news(days: int = 30) -> int:
    """
    Удаляет записи о показанных новостях старше N дней.
    Защищает БД от бесконечного роста.

    Запускай раз в сутки или раз в неделю.
    Возвращает количество удалённых записей.
    """
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
# ОПЕРАЦИИ С РАСХОДАМИ
# ============================================================
def add_expense(
    user_id: int, amount: float, currency: str, category: str, description: str
) -> int:
    """Сохраняет трату и возвращает её id."""
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
    """Возвращает расходы пользователя за последние N дней."""
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
    """Возвращает сумму трат по категориям за последние N дней, убывая."""
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
# ОНБОРДИНГ
# ============================================================

def is_user_onboarded(telegram_id: int) -> bool:
    """Возвращает True если пользователь прошёл онбординг."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT is_onboarded FROM users WHERE telegram_id = ?",
            (telegram_id,),
        ).fetchone()
        return bool(row and row["is_onboarded"])


def update_user_email_credentials(
    telegram_id: int, gmail_user: str, gmail_app_password: str
) -> None:
    """Сохраняет Gmail-кредентиалы пользователя."""
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
    """Помечает онбординг завершённым."""
    with get_db() as conn:
        conn.execute(
            "UPDATE users SET is_onboarded = 1, updated_at = datetime('now') WHERE telegram_id = ?",
            (telegram_id,),
        )


def get_user_email_credentials(telegram_id: int) -> tuple[str, str] | None:
    """
    Возвращает (gmail_user, gmail_app_password) или None если не заданы.
    """
    with get_db() as conn:
        row = conn.execute(
            "SELECT gmail_user, gmail_app_password FROM users WHERE telegram_id = ?",
            (telegram_id,),
        ).fetchone()
        if row and row["gmail_user"] and row["gmail_app_password"]:
            return row["gmail_user"], row["gmail_app_password"]
        return None


# ============================================================
# ТОЧКА ВХОДА ДЛЯ САМОПРОВЕРКИ
# ============================================================
if __name__ == "__main__":
    # Запусти этот файл напрямую, чтобы создать БД и проверить,
    # что всё работает: python database.py
    init_db()
    print("✅ БД инициализирована")

    # Мини-тест
    user = get_or_create_user(
        telegram_id=12345,
        interests=["AI", "стартапы"]
    )
    print(f"✅ Юзер создан/найден: {user}")

    if not is_news_shown(user["id"], "https://example.com/test"):
        mark_news_shown(user["id"], "https://example.com/test", "Test Article")
        print("✅ Новость помечена показанной")

    print(f"✅ Проверка повтора: {is_news_shown(user['id'], 'https://example.com/test')}")