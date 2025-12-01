"""Simple session manager to track active Claude SDK clients."""

import asyncio
import logging
from typing import Dict, Optional
from claude_agent_sdk import ClaudeSDKClient

logger = logging.getLogger(__name__)


class SessionManager:
    """Manages active Claude SDK client instances for interrupt support."""

    def __init__(self):
        self._sessions: Dict[str, ClaudeSDKClient] = {}
        self._lock = asyncio.Lock()

    async def register(self, session_id: str, client: ClaudeSDKClient):
        """Register an active client session."""
        async with self._lock:
            self._sessions[session_id] = client
            logger.info(f"Registered session: {session_id}")

    async def unregister(self, session_id: str):
        """Unregister a session when it completes."""
        async with self._lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
                logger.info(f"Unregistered session: {session_id}")

    async def get_client(self, session_id: str) -> Optional[ClaudeSDKClient]:
        """Get the client for a session."""
        async with self._lock:
            return self._sessions.get(session_id)

    async def interrupt(self, session_id: str) -> bool:
        """
        Interrupt a session.

        Returns:
            True if session was found and interrupted, False otherwise
        """
        async with self._lock:
            client = self._sessions.get(session_id)
            if not client:
                logger.warning(f"Session {session_id} not found for interrupt")
                return False

        try:
            # Call interrupt outside the lock to avoid blocking other operations
            await client.interrupt()
            logger.info(f"Successfully interrupted session {session_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to interrupt session {session_id}: {e}", exc_info=True)
            return False


# Global session manager instance
_manager = SessionManager()


def get_session_manager() -> SessionManager:
    """Get the global session manager instance."""
    return _manager
