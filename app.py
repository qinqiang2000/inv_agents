"""Main FastAPI application for Invoice Field Recommender Agent."""

import logging
import os
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI

# Load environment variables from .env.prod
load_dotenv('.env.prod')
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from api.endpoints import router

# Configure logging with environment variable support
log_level = os.getenv('LOG_LEVEL', 'DEBUG')
logging.basicConfig(
    level=getattr(logging, log_level.upper()),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Invoice Field Recommender Agent",
    description="AI agent for recommending UBL invoice field values based on historical data",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
static_path = Path(__file__).parent / "static"
if static_path.exists():
    app.mount("/static", StaticFiles(directory=str(static_path)), name="static")

# Include API router
app.include_router(router)


@app.get("/")
async def root():
    """Serve the chat UI."""
    chat_html = Path(__file__).parent / "static" / "chat.html"
    if chat_html.exists():
        return FileResponse(chat_html)
    return {"message": "Invoice Field Recommender Agent API", "docs": "/docs"}


@app.on_event("startup")
async def startup_event():
    """Application startup event."""
    logger.info("Starting Invoice Field Recommender Agent")
    logger.info(f"Working directory: {Path.cwd()}")
    logger.info(f"ANTHROPIC_BASE_URL: {os.getenv('ANTHROPIC_BASE_URL')}")
    logger.info(f"ANTHROPIC_MODEL: {os.getenv('ANTHROPIC_MODEL')}")


@app.on_event("shutdown")
async def shutdown_event():
    """Application shutdown event."""
    logger.info("Shutting down Invoice Field Recommender Agent")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
