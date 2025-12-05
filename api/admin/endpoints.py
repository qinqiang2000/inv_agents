"""Admin API endpoints for configuration management and data synchronization."""

import logging
from typing import Dict
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from pathlib import Path
from sse_starlette.sse import EventSourceResponse

# Import from parent api package (absolute import)
from api.config_service import config_manager

# Import from same package (relative import)
from .sync_service import (
    sync_lock_manager,
    stream_basic_data_sync,
    stream_invoice_sync
)
from .sync_models import (
    BasicDataSyncRequest,
    InvoiceSyncRequest,
    SyncStatusResponse
)

logger = logging.getLogger(__name__)

admin_router = APIRouter(prefix="/admin", tags=["admin"])


# ============================================================================
# Configuration Management Models
# ============================================================================

class SwitchConfigRequest(BaseModel):
    """Request model for switching configuration."""
    config_name: str


class SwitchConfigResponse(BaseModel):
    """Response model for switching configuration."""
    success: bool
    message: str
    current_config: str
    env_snapshot: dict


# ============================================================================
# Configuration Management Endpoints
# ============================================================================

@admin_router.get("")
@admin_router.get("/")
async def admin_page():
    """Serve the admin UI."""
    admin_html = Path(__file__).parent.parent.parent / "static" / "admin.html"
    if admin_html.exists():
        return FileResponse(admin_html)
    raise HTTPException(status_code=404, detail="Admin page not found")


@admin_router.get("/api/configs")
async def get_configs():
    """
    Get all available configurations.

    Returns:
        List of configuration objects with name, description, base_url, and is_active flag
    """
    configs = config_manager.get_available_configs()
    current = config_manager.get_current_config_name()
    env_snapshot = config_manager.get_current_env_snapshot()

    return {
        "configs": configs,
        "current_config": current,
        "env_snapshot": env_snapshot
    }


@admin_router.post("/api/switch")
async def switch_config(request: SwitchConfigRequest) -> SwitchConfigResponse:
    """
    Switch to a different model configuration.

    Args:
        request: Contains config_name to switch to

    Returns:
        SwitchConfigResponse with success status and current configuration
    """
    logger.info(f"Switching config to: {request.config_name}")

    success = config_manager.switch_config(request.config_name)

    if success:
        return SwitchConfigResponse(
            success=True,
            message=f"Successfully switched to {request.config_name}",
            current_config=config_manager.get_current_config_name(),
            env_snapshot=config_manager.get_current_env_snapshot()
        )
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown configuration: {request.config_name}"
        )


@admin_router.get("/api/current")
async def get_current_config():
    """
    Get the current active configuration details.

    Returns:
        Current configuration name and environment snapshot
    """
    config = config_manager.get_current_config()
    return {
        "name": config.name,
        "description": config.description,
        "base_url": config.base_url,
        "model": config.model,
        "env_snapshot": config_manager.get_current_env_snapshot()
    }


# ============================================================================
# Data Synchronization Endpoints
# ============================================================================

@admin_router.post("/api/sync/basic-data")
async def sync_basic_data(request: BasicDataSyncRequest):
    """
    Trigger basic data export (currencies, tax codes, payment means, etc.).

    Exports master data from database to context files. Streams progress and logs
    via Server-Sent Events (SSE).

    Args:
        request: Sync request parameters (dry_run flag)

    Returns:
        EventSourceResponse: SSE stream with sync_started, log_message, sync_completed events

    Raises:
        HTTPException 409: If basic data sync is already running
    """
    # Attempt to acquire sync lock
    if not await sync_lock_manager.acquire("basic-data"):
        raise HTTPException(
            status_code=409,
            detail="Basic data sync is already running. Please wait for it to complete."
        )

    # Return SSE stream (lock will be released in stream_basic_data_sync generator)
    return EventSourceResponse(
        stream_basic_data_sync(request, "basic-data"),
        media_type="text/event-stream"
    )


@admin_router.post("/api/sync/invoices")
async def sync_invoices(request: InvoiceSyncRequest):
    """
    Trigger invoice data export with incremental support.

    Exports historical invoice data in UBL 2.1 JSON format, organized by tenant
    and country. Supports both full and incremental export modes. Streams progress
    and logs via Server-Sent Events (SSE).

    Args:
        request: Sync request parameters (incremental, tenant_id, threads, compress, dry_run)

    Returns:
        EventSourceResponse: SSE stream with sync_started, log_message, progress_update,
                            sync_completed events

    Raises:
        HTTPException 409: If invoice sync is already running
    """
    # Attempt to acquire sync lock
    if not await sync_lock_manager.acquire("invoices"):
        raise HTTPException(
            status_code=409,
            detail="Invoice sync is already running. Please wait for it to complete."
        )

    # Return SSE stream (lock will be released in stream_invoice_sync generator)
    return EventSourceResponse(
        stream_invoice_sync(request, "invoices"),
        media_type="text/event-stream"
    )


@admin_router.get("/api/sync/status", response_model=Dict[str, SyncStatusResponse])
async def get_sync_status():
    """
    Get current sync status for all script types.

    Returns:
        Dict with sync status for basic_data and invoices
    """
    return {
        "basic_data": sync_lock_manager.get_status("basic-data"),
        "invoices": sync_lock_manager.get_status("invoices")
    }
