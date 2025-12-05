"""
Queue-based logging handler for streaming logs to SSE clients.

This module provides a custom logging handler that pushes log records to an
asyncio queue, enabling real-time log streaming from sync worker threads.
"""

import logging
import asyncio
from datetime import datetime
from typing import Optional


class QueueLoggingHandler(logging.Handler):
    """
    Thread-safe logging handler that pushes log records to asyncio queue.

    Used to stream logs from sync worker threads (running in ThreadPoolExecutor)
    to SSE response generators (running in asyncio event loop).

    Example:
        >>> log_queue = asyncio.Queue()
        >>> handler = QueueLoggingHandler(log_queue)
        >>> logger = logging.getLogger('my_sync_task')
        >>> logger.addHandler(handler)
        >>>
        >>> # In worker thread
        >>> logger.info("Processing record 1/100")
        >>>
        >>> # In asyncio coroutine
        >>> log_entry = await log_queue.get()
        >>> # Stream to SSE client...
    """

    def __init__(self, queue: asyncio.Queue):
        """
        Initialize the handler.

        Args:
            queue: Asyncio queue to push log records to
        """
        super().__init__()
        self.queue = queue
        self.formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s'
        )

    def emit(self, record: logging.LogRecord):
        """
        Emit log record to queue in thread-safe manner.

        This method is called from worker threads, so we use
        call_soon_threadsafe to safely add items to the asyncio queue.

        Args:
            record: The log record to emit
        """
        try:
            log_entry = {
                "level": record.levelname,
                "message": self.format(record),
                "timestamp": datetime.utcnow().isoformat(),
                "logger": record.name
            }
            # Thread-safe queue insertion
            self.queue._loop.call_soon_threadsafe(
                self.queue.put_nowait, log_entry
            )
        except Exception:
            self.handleError(record)
