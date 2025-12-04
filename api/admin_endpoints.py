"""Admin API endpoints for configuration management."""

import logging
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from pathlib import Path
from .config_service import config_manager

logger = logging.getLogger(__name__)

admin_router = APIRouter(prefix="/admin", tags=["admin"])


class SwitchConfigRequest(BaseModel):
    """Request model for switching configuration."""
    config_name: str


class SwitchConfigResponse(BaseModel):
    """Response model for switching configuration."""
    success: bool
    message: str
    current_config: str
    env_snapshot: dict


@admin_router.get("")
@admin_router.get("/")
async def admin_page():
    """Serve the admin UI."""
    admin_html = Path(__file__).parent.parent / "static" / "admin.html"
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
