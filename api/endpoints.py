"""API route handlers."""

import logging
import json
from fastapi import APIRouter, HTTPException, Request
from sse_starlette.sse import EventSourceResponse
from .models import QueryRequest
from . import agent_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["agent"])


@router.post("/query")
async def query_agent(request: QueryRequest, http_request: Request):
    """
    Query the Claude agent with streaming response.

    Args:
        request: Query request containing tenant_id, prompt, skill, etc.
        http_request: FastAPI Request object for accessing HTTP request details

    Returns:
        Server-Sent Events (SSE) stream with agent responses

    Example:
        ```
        POST /api/query
        {
          "tenant_id": "1",
          "prompt": "推荐unitCode for 咖啡机",
          "skill": "invoice-field-recommender",
          "language": "中文",
          "session_id": null,
          "country_code": "MY"
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
    """
    try:
        # Print all request body information
        request_dict = request.model_dump()
        logger.info(f"Request body: {json.dumps(request_dict, ensure_ascii=False, indent=2)}")
        
        # Print HTTP request information
        logger.info(f"HTTP Method: {http_request.method}")
        logger.info(f"URL: {http_request.url}")
        logger.info(f"Headers: {dict(http_request.headers)}")
        logger.info(f"Query params: {dict(http_request.query_params)}")
        logger.info(f"Client: {http_request.client}")
        
        logger.info(
            f"Received query request: tenant={request.tenant_id}, "
            f"skill={request.skill}, session={request.session_id}"
        )

        return EventSourceResponse(
            agent_service.stream_response(request),
            media_type="text/event-stream"
        )

    except Exception as e:
        logger.error(f"Error in query_agent: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "invoice-field-recommender-agent"}
