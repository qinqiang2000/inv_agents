"""API route handlers."""

import logging
import json
import os
from datetime import datetime
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sse_starlette.sse import EventSourceResponse
from .models import QueryRequest
from . import agent_service
from .session_manager import session_manager


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["agent"])

# Base directory for storing pending invoices (tenant-isolated)
TENANT_DATA_DIR = "tenant-data"


def save_invoice_context(tenant_id: str, country_code: str, context: str) -> str:
    """
    Save invoice context to file.
    
    Args:
        tenant_id: Tenant identifier
        country_code: Country code
        context: Invoice data in UBL 2.1 format
        
    Returns:
        File path where the context was saved
    """
    # Create directory if not exists: tenant-data/{tenant_id}/pending-invoices/
    pending_dir = os.path.join(TENANT_DATA_DIR, tenant_id, "pending-invoices")
    os.makedirs(pending_dir, exist_ok=True)
    
    # Generate filename with timestamp (to milliseconds)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]  # Remove last 3 digits to get milliseconds
    filename = f"draft_{country_code}_{timestamp}.xml"
    file_path = os.path.join(pending_dir, filename)
    
    # Write context to file
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(context)
    
    logger.info(f"Saved invoice context to: {file_path}")
    return file_path


@router.post("/query")
async def query_agent(request: Request):
    """
    Query the Claude agent with streaming response.

    Args:
        request: FastAPI Request object for accessing HTTP request details

    Returns:
        Server-Sent Events (SSE) stream with agent responses

    Examples:
        New Session (requires country_code and language):
        ```
        POST /api/query
        {
          "tenant_id": "1",
          "prompt": "推荐unitCode for 咖啡机",
          "skill": "invoice-field-recommender",
          "language": "中文",
          "session_id": null,
          "country_code": "MY",
          "context": "<Invoice>...</Invoice>"
        }
        ```

        Continuation Session (country_code and language optional):
        ```
        POST /api/query
        {
          "tenant_id": "1",
          "prompt": "继续前面的对话",
          "session_id": "abc-123-def"
        }
        ```

    Response Stream:
        ```
        event: session_created
        data: {"session_id": "abc-123"}

        event: assistant_message
        data: {"content": "正在查找..."}

        event: tool_use
        data: {"tool": "Grep", "input": "..."}

        event: result
        data: {"session_id": "abc-123", "duration_ms": 1234, ...}
        ```

    Validation Rules:
        - New sessions (session_id is null/absent): Require country_code and language
        - Continuation sessions (session_id present): country_code and language are optional
    """
    try:
        # Parse and validate request body
        body = await request.json()
        
        try:
            query_request = QueryRequest(**body)
        except ValidationError as e:
            # Return 422 with detailed validation errors (industry best practice)
            errors = []
            for error in e.errors():
                field = ".".join(str(loc) for loc in error["loc"])
                errors.append({
                    "field": field,
                    "message": error["msg"],
                    "type": error["type"]
                })
            logger.warning(f"Validation error: {errors}")
            return JSONResponse(
                status_code=422,
                content={
                    "error": "Validation Error",
                    "message": "Request validation failed",
                    "details": errors
                }
            )
        
        # Print request body information
        request_dict = query_request.model_dump()
        # Log context partially if present (first 200 chars)
        log_dict = request_dict.copy()
        if log_dict.get("context"):
            context_preview = log_dict["context"][:200] + "..." if len(log_dict["context"]) > 200 else log_dict["context"]
            log_dict["context"] = f"[{len(request_dict['context'])} chars] {context_preview}"
        logger.info(f"Request body: {json.dumps(log_dict, ensure_ascii=False, indent=2)}")
        
        logger.info(
            f"Received query request: tenant={query_request.tenant_id}, "
            f"skill={query_request.skill}, session={query_request.session_id}"
        )

        # Save invoice context if conditions are met
        invoice_file_path = None
        if query_request.context and query_request.skill == "invoice-field-recommender":
            invoice_file_path = save_invoice_context(
                tenant_id=query_request.tenant_id,
                country_code=query_request.country_code,
                context=query_request.context
            )

        return EventSourceResponse(
            agent_service.stream_response(query_request, invoice_file_path=invoice_file_path),
            media_type="text/event-stream"
        )

    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in request body: {str(e)}")
        return JSONResponse(
            status_code=400,
            content={
                "error": "Bad Request",
                "message": "Invalid JSON in request body",
                "details": str(e)
            }
        )
    except Exception as e:
        logger.error(f"Error in query_agent: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "invoice-field-recommender-agent"}


@router.post("/interrupt/{session_id}")
async def interrupt_session(session_id: str):
    """
    Interrupt an ongoing agent session.

    Args:
        session_id: The session ID to interrupt

    Returns:
        {"success": True} if session was found and interrupted
        {"success": False} if session doesn't exist or interrupt failed
    """
    logger.info(f"Received interrupt request for session: {session_id}")
    success = await session_manager.interrupt(session_id)
    return {"success": success, "session_id": session_id}



