"""Claude SDK integration service for agent queries."""

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import AsyncGenerator, Optional
from claude_agent_sdk import (
    ClaudeSDKClient,
    ClaudeAgentOptions,
    UserMessage,
    AssistantMessage,
    SystemMessage,
    ResultMessage,
    TextBlock,
    ToolUseBlock
)
from .models import QueryRequest
from .session_manager import session_manager


logger = logging.getLogger(__name__)

# Timeout for waiting on first message from Claude SDK (seconds)
FIRST_MESSAGE_TIMEOUT = int(os.getenv("CLAUDE_FIRST_MESSAGE_TIMEOUT", "120"))

# Directory paths for tenant isolation
AGENTS_ROOT = Path(__file__).resolve().parent.parent  # /agents
CONTEXT_DIR = AGENTS_ROOT / "context"                 # /agents/context (public data)
TENANT_DATA_DIR = AGENTS_ROOT / "tenant-data"         # /agents/tenant-data (tenant-specific data)


def build_initial_prompt(
    tenant_id: str,
    user_prompt: str,
    skill: Optional[str] = None,
    country_code: Optional[str] = None,
    language: str = "中文",
    invoice_file_path: Optional[str] = None,
) -> str:
    """
    Build the initial prompt for new conversations.

    Args:
        tenant_id: Tenant identifier
        user_prompt: User's query
        skill: Optional skill name to use
        country_code: Country code for invoice
        language: Response language
        invoice_file_path: Path to the saved invoice file

    Returns:
        Formatted prompt string
    """
    parts = ["# 任务"]
    if skill:
        parts.append(f"使用的skill：{skill}")
    parts.append(user_prompt)
    
    parts.append("\n# 上下文")
    parts.append(f"租户：{tenant_id}")

    if country_code:
        parts.append(f"发票开具国家代码：{country_code}")

    if invoice_file_path:
        parts.append(f"Invoice File Path：{invoice_file_path}")

    parts.append("\n# 约束")
    if skill:
        parts.append(f"严格按照skill：{skill} 的要求进行输出，不要输出任何其他内容")
    parts.append(f"所有的输出使用语言：{language}")

    return "\n".join(parts)


def extract_todos_from_tool(tool_block: ToolUseBlock) -> Optional[list]:
    """
    Extract todos array from TodoWrite tool input.

    Args:
        tool_block: ToolUseBlock from Claude SDK

    Returns:
        List of todo objects or None if not a TodoWrite block
    """
    if tool_block.name == "TodoWrite" and isinstance(tool_block.input, dict):
        return tool_block.input.get("todos", [])
    return None


def format_sse_message(event_type: str, data: any) -> dict:
    """
    Format a message as Server-Sent Events (SSE) format.

    Args:
        event_type: Event type (e.g., 'user_message', 'assistant_message')
        data: Event data (will be JSON-serialized if not a string)

    Returns:
        Dict with 'event' and 'data' keys for EventSourceResponse
    """
    if isinstance(data, str):
        data_dict = {"content": data}
    else:
        data_dict = data

    # Explicitly convert to JSON to ensure proper formatting
    ret = {"event": event_type, "data": json.dumps(data_dict, ensure_ascii=False)}
    logger.info(f"format_sse_message: {ret}")
    return ret


async def stream_response(
    request: QueryRequest,
    invoice_file_path: Optional[str] = None
) -> AsyncGenerator[str, None]:
    """
    Stream Claude SDK responses as Server-Sent Events.

    Args:
        request: Query request with tenant, prompt, skill, etc.
        invoice_file_path: Path to the saved invoice context file

    Yields:
        SSE-formatted messages
    """
    # Immediately yield a heartbeat to keep connection alive
    yield format_sse_message("heartbeat", {"status": "connecting"})
    
    try:
        # Build prompt based on whether this is a new or resumed session
        if request.session_id:
            # Resume existing session
            prompt = request.prompt
            logger.info(f"Resuming session: {request.session_id} \n prompt: {prompt}")
        else:
            # New session - assemble full prompt
            prompt = build_initial_prompt(
                tenant_id=request.tenant_id,
                user_prompt=request.prompt,
                skill=request.skill,
                country_code=request.country_code,
                language=request.language,
                invoice_file_path=invoice_file_path,
            )
            logger.info(f"Starting new session: \n prompt: {prompt}")

        # Build tenant-specific directory for isolation
        tenant_dir = TENANT_DATA_DIR / request.tenant_id

        # Configure Claude SDK options with tenant isolation
        options = ClaudeAgentOptions(
            system_prompt={"type": "preset", "preset": "claude_code"},
            setting_sources=["project"],  # Load CLAUDE.md from project
            allowed_tools=["Skill", "Read", "Grep", "Glob", "Bash", "WebFetch", "WebSearch"],
            resume=request.session_id,  # None for new, sessionId for resume
            max_buffer_size=10 * 1024 * 1024,  # 10MB buffer
            cwd=str(CONTEXT_DIR),  # Set working directory to public data
            add_dirs=[str(tenant_dir)] if tenant_dir.exists() else []  # Add tenant directory dynamically
        )

        logger.info(f"Tenant isolation: cwd={CONTEXT_DIR}, add_dirs={[str(tenant_dir)] if tenant_dir.exists() else []}")

        logger.info("Creating ClaudeSDKClient...")
        
        # Stream responses from Claude SDK
        async with ClaudeSDKClient(options=options) as client:
            logger.info("ClaudeSDKClient connected, sending query...")
            yield format_sse_message("heartbeat", {"status": "connected"})
            
            await client.query(prompt)
            logger.info("Query sent, waiting for response...")
            yield format_sse_message("heartbeat", {"status": "processing"})

            # Track session_id for new sessions
            session_id_sent = False
            actual_session_id = request.session_id  # Start with existing session_id if resuming
            first_message_received = False
            session_registered = False

            # If resuming, register session immediately for interrupt support
            if request.session_id:
                await session_manager.register(request.session_id, client)
                session_registered = True

            try:
                async for msg in client.receive_response():
                    if not first_message_received:
                        first_message_received = True
                        logger.info(f"First message received: {type(msg).__name__}")
                    
                    # Catch system init message with session_id (first message)
                    if isinstance(msg, SystemMessage):
                        logger.debug(f"SystemMessage: subtype={getattr(msg, 'subtype', None)}, data={getattr(msg, 'data', None)}")
                        if hasattr(msg, 'subtype') and msg.subtype == 'init' and not request.session_id and not session_id_sent:
                            # Extract session_id from data
                            if isinstance(msg.data, dict) and 'session_id' in msg.data:
                                actual_session_id = msg.data['session_id']
                                yield format_sse_message("session_created", {
                                    "session_id": actual_session_id
                                })
                                session_id_sent = True
                                logger.info(f"Created new session: {actual_session_id}")
                                # Register session for interrupt support
                                await session_manager.register(actual_session_id, client)
                                session_registered = True

                    # Also track session_id from ResultMessage (as fallback)
                    if isinstance(msg, ResultMessage):
                        actual_session_id = msg.session_id
                        if not request.session_id and not session_id_sent:
                            yield format_sse_message("session_created", {
                                "session_id": msg.session_id
                            })
                            session_id_sent = True
                            logger.info(f"Created new session (from result): {msg.session_id}")
                            # Register session for interrupt support (fallback)
                            if not session_registered:
                                await session_manager.register(msg.session_id, client)
                                session_registered = True

                    # Process different message types
                    if isinstance(msg, AssistantMessage):
                        for block in msg.content:
                            if isinstance(block, TextBlock):
                                # 完整记录 Agent 消息（INFO级别）
                                logger.info(f"[Agent] {block.text}")
                                yield format_sse_message("assistant_message", block.text)
                            elif isinstance(block, ToolUseBlock):
                                # 完整记录工具调用（INFO级别）
                                logger.info(f"[Tool] {block.name} - Input: {block.input}")

                                # Check for TodoWrite and emit todos
                                if block.name == "TodoWrite":
                                    todos = extract_todos_from_tool(block)
                                    if todos:
                                        logger.info(f"[TodoWrite] Emitting {len(todos)} todos")
                                        yield format_sse_message("todos_update", {"todos": todos})

                    elif isinstance(msg, ResultMessage):
                        # Send final result with metadata
                        yield format_sse_message("result", {
                            "session_id": msg.session_id,
                            "duration_ms": msg.duration_ms,
                            "is_error": msg.is_error,
                            "num_turns": msg.num_turns
                        })

                        logger.info(
                            f"Session {msg.session_id} completed: "
                            f"duration={msg.duration_ms}ms, turns={msg.num_turns}, error={msg.is_error}"
                        )
            
                if not first_message_received:
                    logger.warning("No messages received from Claude SDK")
            finally:
                # Unregister session when streaming completes or errors
                if session_registered and actual_session_id:
                    await session_manager.unregister(actual_session_id)

    except Exception as e:
        logger.error(f"Error in stream_response: {str(e)}", exc_info=True)
        yield format_sse_message("error", {
            "message": str(e),
            "type": type(e).__name__
        })
