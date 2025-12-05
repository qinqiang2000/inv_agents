"""
Core synchronization service for streaming export script execution.

This module provides lock management and SSE streaming for background data export tasks.
"""

import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator, Dict, Any

from .logging_handler import QueueLoggingHandler
from .sync_models import BasicDataSyncRequest, InvoiceSyncRequest
from api.agent_service import format_sse_message

logger = logging.getLogger(__name__)


class SyncLockManager:
    """
    Manages sync locks to prevent concurrent execution.

    Provides in-memory locks (asyncio.Lock) to prevent multiple concurrent syncs
    of the same type within a single process. Works in conjunction with file-based
    locks in export scripts to prevent cross-process conflicts.
    """

    def __init__(self):
        self._locks = {
            "basic-data": asyncio.Lock(),
            "invoices": asyncio.Lock()
        }
        self._current_sync = {
            "basic-data": None,
            "invoices": None
        }

    async def acquire(self, script_type: str) -> bool:
        """
        Attempt to acquire lock for a sync type (non-blocking).

        Args:
            script_type: Type of sync ("basic-data" or "invoices")

        Returns:
            True if lock acquired, False if already locked
        """
        lock = self._locks.get(script_type)
        if not lock or lock.locked():
            return False

        await lock.acquire()
        self._current_sync[script_type] = {
            "start_time": datetime.utcnow().isoformat(),
            "status": "running"
        }
        return True

    def release(self, script_type: str):
        """
        Release lock for a sync type.

        Args:
            script_type: Type of sync ("basic-data" or "invoices")
        """
        lock = self._locks.get(script_type)
        if lock and lock.locked():
            lock.release()
        self._current_sync[script_type] = None

    def get_status(self, script_type: str) -> Dict[str, Any]:
        """
        Get current sync status for a script type.

        Args:
            script_type: Type of sync ("basic-data" or "invoices")

        Returns:
            Dict with is_running flag and current_sync metadata
        """
        return {
            "is_running": self._locks.get(script_type, asyncio.Lock()).locked(),
            "current_sync": self._current_sync.get(script_type)
        }


# Global singleton instance
sync_lock_manager = SyncLockManager()


async def stream_basic_data_sync(
    request: BasicDataSyncRequest,
    script_type: str
) -> AsyncGenerator[dict, None]:
    """
    Stream basic data export progress via SSE.

    Runs export_basic_data_to_context() in a thread pool and streams logs/progress
    to the client via Server-Sent Events.

    Args:
        request: Sync request parameters
        script_type: Script type for lock management ("basic-data")

    Yields:
        SSE-formatted messages (sync_started, log_message, sync_completed, error)
    """
    log_queue = asyncio.Queue()
    start_time = datetime.utcnow()

    try:
        # Start event
        yield format_sse_message("sync_started", {
            "script": "basic-data",
            "mode": "full",
            "dry_run": request.dry_run,
            "timestamp": start_time.isoformat()
        })

        # Import export logic (avoid circular dependencies)
        sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'script'))
        from export_basic_data import export_basic_data_to_context

        # Define sync worker function
        def sync_worker():
            return export_basic_data_to_context(
                dry_run=request.dry_run,
                log_queue=log_queue
            )

        # Run sync in thread pool to avoid blocking asyncio
        sync_task = asyncio.create_task(asyncio.to_thread(sync_worker))

        # Stream logs while sync is running
        while not sync_task.done():
            try:
                log_entry = await asyncio.wait_for(log_queue.get(), timeout=0.5)
                yield format_sse_message("log_message", log_entry)
            except asyncio.TimeoutError:
                # Send heartbeat to keep connection alive
                yield format_sse_message("heartbeat", {"status": "running"})

        # Drain remaining logs from queue
        while not log_queue.empty():
            log_entry = log_queue.get_nowait()
            yield format_sse_message("log_message", log_entry)

        # Get final result
        result = await sync_task
        duration = (datetime.utcnow() - start_time).total_seconds()

        # Send completion event
        yield format_sse_message("sync_completed", {
            "status": "success" if result.get("success") else "error",
            "duration_seconds": duration,
            "summary": result
        })

    except Exception as e:
        logger.exception("Basic data sync failed")
        yield format_sse_message("error", {
            "message": str(e),
            "type": type(e).__name__
        })
    finally:
        # Always release lock when generator exits
        sync_lock_manager.release(script_type)
        logger.info(f"Released lock for {script_type}")


async def stream_invoice_sync(
    request: InvoiceSyncRequest,
    script_type: str
) -> AsyncGenerator[dict, None]:
    """
    Stream invoice export progress via SSE.

    Runs InvoiceExporter in a thread pool and streams logs/progress to the client
    via Server-Sent Events.

    Args:
        request: Sync request parameters
        script_type: Script type for lock management ("invoices")

    Yields:
        SSE-formatted messages (sync_started, log_message, progress_update, sync_completed, error)
    """
    log_queue = asyncio.Queue()
    progress_queue = asyncio.Queue()
    start_time = datetime.utcnow()

    try:
        # Start event
        yield format_sse_message("sync_started", {
            "script": "invoices",
            "mode": "incremental" if request.incremental else "full",
            "tenant_id": request.tenant_id,
            "dry_run": request.dry_run,
            "timestamp": start_time.isoformat()
        })

        # Import export logic
        sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'script'))
        from export_invoice_data import InvoiceExporter

        # Define sync worker function
        def sync_worker():
            exporter = InvoiceExporter(
                num_threads=request.threads,
                compress=request.compress,
                dry_run=request.dry_run,
                incremental=request.incremental,
                tenant_id=request.tenant_id,
                log_queue=log_queue,
                progress_queue=progress_queue
            )

            if request.incremental:
                return exporter.export_incremental()
            else:
                return exporter.export_all()

        # Run sync in thread pool
        sync_task = asyncio.create_task(asyncio.to_thread(sync_worker))

        # Stream logs and progress while sync is running
        last_heartbeat = datetime.utcnow()
        while not sync_task.done():
            # Check for logs (short timeout)
            try:
                log_entry = await asyncio.wait_for(log_queue.get(), timeout=0.1)
                yield format_sse_message("log_message", log_entry)
                continue
            except asyncio.TimeoutError:
                pass

            # Check for progress updates (short timeout)
            try:
                progress = await asyncio.wait_for(progress_queue.get(), timeout=0.1)
                yield format_sse_message("progress_update", progress)
                continue
            except asyncio.TimeoutError:
                pass

            # Send heartbeat every 30 seconds to keep connection alive
            now = datetime.utcnow()
            if (now - last_heartbeat).total_seconds() > 30:
                yield format_sse_message("heartbeat", {"status": "running"})
                last_heartbeat = now

            # Small sleep to avoid tight loop
            await asyncio.sleep(0.5)

        # Drain remaining logs and progress updates
        while not log_queue.empty():
            log_entry = log_queue.get_nowait()
            yield format_sse_message("log_message", log_entry)

        while not progress_queue.empty():
            progress = progress_queue.get_nowait()
            yield format_sse_message("progress_update", progress)

        # Get final result
        result = await sync_task
        duration = (datetime.utcnow() - start_time).total_seconds()

        # Send completion event
        status = "success" if result.get("success") else "partial"
        yield format_sse_message("sync_completed", {
            "status": status,
            "duration_seconds": duration,
            "summary": result
        })

    except Exception as e:
        logger.exception("Invoice sync failed")
        yield format_sse_message("error", {
            "message": str(e),
            "type": type(e).__name__
        })
    finally:
        # Always release lock when generator exits
        sync_lock_manager.release(script_type)
        logger.info(f"Released lock for {script_type}")
