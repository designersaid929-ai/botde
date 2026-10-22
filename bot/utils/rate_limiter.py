import time
import asyncio
from typing import Dict, Tuple


class UserRateLimiter:
    """
    Per-user cooldown manager to prevent flooding requests and hitting Instagram rate limits.
    """
    def __init__(self, cooldown_seconds: int = 4):
        self.cooldown_seconds = cooldown_seconds
        self._user_last_action: Dict[int, float] = {}
        self._lock = asyncio.Lock()

    async def check(self, user_id: int) -> Tuple[bool, float]:
        """
        Checks if the user is allowed to perform an action.
        Returns (is_allowed, remaining_seconds_to_wait).
        """
        async with self._lock:
            now = time.time()
            last_time = self._user_last_action.get(user_id, 0.0)
            elapsed = now - last_time

            if elapsed < self.cooldown_seconds:
                remaining = self.cooldown_seconds - elapsed
                return False, round(remaining, 1)

            self._user_last_action[user_id] = now
            return True, 0.0

    async def reset(self, user_id: int) -> None:
        """Resets cooldown for a user."""
        async with self._lock:
            self._user_last_action.pop(user_id, None)

    async def cleanup_idle(self, max_idle_seconds: int = 3600) -> None:
        """Removes entries older than max_idle_seconds to prevent memory growth."""
        async with self._lock:
            now = time.time()
            expired_users = [
                u for u, t in self._user_last_action.items()
                if now - t > max_idle_seconds
            ]
            for u in expired_users:
                del self._user_last_action[u]
