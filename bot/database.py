"""SQLite database for storing user sessions (JWT tokens mapped to Telegram chat IDs)."""

import aiosqlite
import time
from typing import Optional, Dict, Any

from bot.config import DB_PATH


async def init_db() -> None:
    """Create the database tables if they don't exist."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_sessions (
                telegram_chat_id INTEGER PRIMARY KEY,
                erp_user_id TEXT,
                access_token TEXT NOT NULL,
                refresh_token TEXT,
                email TEXT,
                full_name TEXT,
                roles TEXT,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS oauth_states (
                state TEXT PRIMARY KEY,
                telegram_chat_id INTEGER NOT NULL,
                created_at REAL NOT NULL
            )
        """)
        await db.commit()


async def save_session(
    telegram_chat_id: int,
    access_token: str,
    refresh_token: str = "",
    erp_user_id: str = "",
    email: str = "",
    full_name: str = "",
    roles: str = "",
) -> None:
    """Save or update a user session."""
    now = time.time()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO user_sessions
                (telegram_chat_id, erp_user_id, access_token, refresh_token, email, full_name, roles, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(telegram_chat_id) DO UPDATE SET
                erp_user_id = excluded.erp_user_id,
                access_token = excluded.access_token,
                refresh_token = CASE WHEN excluded.refresh_token != '' THEN excluded.refresh_token ELSE user_sessions.refresh_token END,
                email = CASE WHEN excluded.email != '' THEN excluded.email ELSE user_sessions.email END,
                full_name = CASE WHEN excluded.full_name != '' THEN excluded.full_name ELSE user_sessions.full_name END,
                roles = CASE WHEN excluded.roles != '' THEN excluded.roles ELSE user_sessions.roles END,
                updated_at = excluded.updated_at
            """,
            (telegram_chat_id, erp_user_id, access_token, refresh_token, email, full_name, roles, now, now),
        )
        await db.commit()


async def get_session(telegram_chat_id: int) -> Optional[Dict[str, Any]]:
    """Get a user session by Telegram chat ID."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM user_sessions WHERE telegram_chat_id = ?",
            (telegram_chat_id,),
        ) as cursor:
            row = await cursor.fetchone()
            if row is None:
                return None
            return dict(row)


async def update_token(telegram_chat_id: int, access_token: str, refresh_token: str = "") -> None:
    """Update the access token (and optionally refresh token) for a session."""
    now = time.time()
    async with aiosqlite.connect(DB_PATH) as db:
        if refresh_token:
            await db.execute(
                "UPDATE user_sessions SET access_token = ?, refresh_token = ?, updated_at = ? WHERE telegram_chat_id = ?",
                (access_token, refresh_token, now, telegram_chat_id),
            )
        else:
            await db.execute(
                "UPDATE user_sessions SET access_token = ?, updated_at = ? WHERE telegram_chat_id = ?",
                (access_token, now, telegram_chat_id),
            )
        await db.commit()


async def delete_session(telegram_chat_id: int) -> None:
    """Delete a user session."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM user_sessions WHERE telegram_chat_id = ?",
            (telegram_chat_id,),
        )
        await db.commit()


async def get_all_sessions() -> list[Dict[str, Any]]:
    """Get all active sessions (for notification polling)."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM user_sessions") as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


# ── OAuth State Management ───────────────────────────────────────────────────

async def save_oauth_state(state: str, telegram_chat_id: int) -> None:
    """Save an OAuth state token linked to a Telegram chat."""
    now = time.time()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO oauth_states (state, telegram_chat_id, created_at) VALUES (?, ?, ?)",
            (state, telegram_chat_id, now),
        )
        await db.commit()


async def get_oauth_state(state: str) -> Optional[int]:
    """Get the Telegram chat ID for an OAuth state, then delete it. Returns None if expired (>10min) or not found."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT telegram_chat_id, created_at FROM oauth_states WHERE state = ?",
            (state,),
        ) as cursor:
            row = await cursor.fetchone()
            if row is None:
                return None
            chat_id, created_at = row
            # Expire after 10 minutes
            if time.time() - created_at > 600:
                await db.execute("DELETE FROM oauth_states WHERE state = ?", (state,))
                await db.commit()
                return None
            # Delete used state
            await db.execute("DELETE FROM oauth_states WHERE state = ?", (state,))
            await db.commit()
            return chat_id


async def cleanup_expired_states() -> None:
    """Remove OAuth states older than 10 minutes."""
    cutoff = time.time() - 600
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM oauth_states WHERE created_at < ?", (cutoff,))
        await db.commit()
