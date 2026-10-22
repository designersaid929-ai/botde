import aiosqlite
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime

DB_PATH = Path(__file__).resolve().parent.parent / "bot_stats.db"

INIT_SQL = """
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    last_name TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS queries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    query_text TEXT,
    query_type TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE INDEX IF NOT EXISTS idx_queries_user ON queries(user_id);
CREATE INDEX IF NOT EXISTS idx_queries_date ON queries(created_at);
"""

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(INIT_SQL)
        await db.commit()

async def track_user(user_id: int, username: Optional[str], first_name: Optional[str], last_name: Optional[str]) -> bool:
    """
    Saves or updates user activity.
    Returns True if this is a newly registered user.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
        is_new = (await cursor.fetchone()) is None

        if is_new:
            await db.execute("""
                INSERT INTO users (user_id, username, first_name, last_name, created_at, last_active)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """, (user_id, username, first_name, last_name))
        else:
            await db.execute("""
                UPDATE users SET
                    username = COALESCE(?, username),
                    first_name = COALESCE(?, first_name),
                    last_name = COALESCE(?, last_name),
                    last_active = CURRENT_TIMESTAMP
                WHERE user_id = ?
            """, (username, first_name, last_name, user_id))

        await db.commit()
        return is_new

async def log_query(user_id: int, query_text: str, query_type: str = "search"):
    """Logs an Instagram search query."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO queries (user_id, query_text, query_type, created_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        """, (user_id, query_text, query_type))
        await db.commit()

async def get_stats() -> Dict:
    """Returns database summary statistics for admin."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM users")
        total_users = (await cursor.fetchone())[0]

        cursor = await db.execute("SELECT COUNT(*) FROM queries")
        total_queries = (await cursor.fetchone())[0]

        cursor = await db.execute("""
            SELECT COUNT(*) FROM queries 
            WHERE date(created_at) = date('now')
        """)
        today_queries = (await cursor.fetchone())[0]

        cursor = await db.execute("""
            SELECT query_text, COUNT(*) as cnt 
            FROM queries 
            GROUP BY query_text 
            ORDER BY cnt DESC 
            LIMIT 5
        """)
        top_queries = [dict(row) for row in [dict(zip(["query", "count"], r)) for r in await cursor.fetchall()]]

        return {
            "total_users": total_users,
            "total_queries": total_queries,
            "today_queries": today_queries,
            "top_queries": top_queries
        }
