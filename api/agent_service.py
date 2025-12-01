"""Claude SDK integration service for agent queries."""

import json
import logging
from typing import AsyncGenerator, Optional
from claude_agent_sdk import (
    ClaudeSDKClient,
    ClaudeAgentOptions,
    UserMessage,
    AssistantMessage,
    ResultMessage,
    TextBlock,
    ToolUseBlock
)
from .models import QueryRequest

logger = logging.getLogger(__name__)


def build_initial_prompt(
    tenant_id: str,
    user_prompt: str,
    skill: Optional[str] = None,
    country_code: Optional[str] = None,
    language: str = "中文",
) -> str:
    """
    Build the initial prompt for new conversations.

    Args:
        tenant_id: Tenant identifier
        user_prompt: User's query
        skill: Optional skill name to use
        language: Response language

    Returns:
        Formatted prompt string
    """
    parts = ["# 上下文"]
    parts.append(f"租户：{tenant_id}")

    if country_code:
        parts.append(f"发票开具国家代码：{country_code}")

    if skill:
        parts.append(f"要使用的skill：{skill}")

    parts.append("\n# 任务")
    parts.append(user_prompt)

    parts.append("\n# 约束")
    parts.append(f"所有的输出使用语言：{language}")

    return "\n".join(parts)


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


async def stream_response(request: QueryRequest) -> AsyncGenerator[str, None]:
    """
    Stream Claude SDK responses as Server-Sent Events.

    Args:
        request: Query request with tenant, prompt, skill, etc.

    Yields:
        SSE-formatted messages
    """
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
            )
            logger.info(f"Starting new session: \n prompt: {prompt}")

        # Configure Claude SDK options
        options = ClaudeAgentOptions(
            system_prompt={"type": "preset", "preset": "claude_code"},
            setting_sources=["project"],  # Load CLAUDE.md from project
            allowed_tools=["Skill", "Read", "Grep", "Glob", "Bash", "WebFetch", "WebSearch"],
            resume=request.session_id  # None for new, sessionId for resume
        )

        # Stream responses from Claude SDK
        async with ClaudeSDKClient(options=options) as client:
            await client.query(prompt)

            async for msg in client.receive_response():
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
                            # yield format_sse_message("tool_use", {
                            #     "tool": block.name,
                            #     "input": str(block.input) if block.input else None
                            # })

                elif isinstance(msg, ResultMessage):
                    # Extract and send session_id for new sessions
                    if not request.session_id:
                        yield format_sse_message("session_created", {
                            "session_id": msg.session_id
                        })
                        logger.info(f"Created new session: {msg.session_id}")

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

    except Exception as e:
        logger.error(f"Error in stream_response: {str(e)}", exc_info=True)
        yield format_sse_message("error", {
            "message": str(e),
            "type": type(e).__name__
        })
