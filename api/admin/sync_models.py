"""
Pydantic models for data synchronization API requests and responses.
"""

from pydantic import BaseModel, Field
from typing import Optional


class BasicDataSyncRequest(BaseModel):
    """Request model for basic data synchronization."""

    dry_run: bool = Field(
        default=False,
        description="Preview mode without writing files or updating state"
    )


class InvoiceSyncRequest(BaseModel):
    """Request model for invoice data synchronization."""

    incremental: bool = Field(
        default=True,
        description="Incremental export mode (only new/updated invoices since last sync)"
    )

    tenant_id: Optional[str] = Field(
        default=None,
        description="Specific tenant ID to export, or None for all tenants"
    )

    threads: int = Field(
        default=4,
        ge=1,
        le=16,
        description="Number of parallel threads for export processing"
    )

    compress: bool = Field(
        default=False,
        description="Enable gzip compression for exported JSON files"
    )

    dry_run: bool = Field(
        default=False,
        description="Preview mode without writing files or updating state"
    )


class SyncStatusResponse(BaseModel):
    """Response model for sync status query."""

    is_running: bool = Field(
        description="Whether a sync operation is currently running"
    )

    start_time: Optional[str] = Field(
        default=None,
        description="ISO timestamp when sync started (if running)"
    )

    script_type: Optional[str] = Field(
        default=None,
        description="Type of sync currently running (basic-data or invoices)"
    )

    params: Optional[dict] = Field(
        default=None,
        description="Parameters of current sync operation"
    )
