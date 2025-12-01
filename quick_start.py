#!/usr/bin/env python3
"""Quick start example for Claude Code SDK."""

import anyio
import sys
from pathlib import Path

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    TextBlock,
    SystemMessage,
    UserMessage,
    ToolUseBlock
)

_prompt1 = """# 任务
根据错误信息、上下文信息，数据信息，从数据中找出符合上下文的最接近的且最新的值作为推荐值

# 错误信息
unitCode错误

# 数据信息
@context/ 包含历史开票成功数据；
一级子目录是租户；二级子目录是国家代码； json文件名称：发票号码+开票时间 
json数据格式符合ubl2.1的格式

# 上下文信息
租户：1
国家：DE
商品名称：DJI RC-N3 Remote Controller 

# tips
商品名称可能不100%字符串相等；相似度高即可 

# 约束
思考过程用"中文"输出，不要用其他语言；
"""

_prompt2 = """从基础数据中查找马来西亚的单位代码中，最匹配"Yashica MG-2 - Cameras"这个商品的单位代码 。只从基础数据找"""

# 从文件读取 SKILL.md 内容作为 _prompt3
_skill_file = Path(__file__).parent / ".claude" / "skills" / "invoice-field-recommender" / "SKILL.md"
_prompt3 = _skill_file.read_text(encoding="utf-8") if _skill_file.exists() else ""
_prompt3 += """
---上下文---
租户：1                                       
国家：MY
商品名称：咖啡机
请推荐该发票所用的字段unitCode
"""

def display_message(msg):
    """Standardized message display function.

    - UserMessage: "User: <content>"
    - AssistantMessage: "Claude: <content>"
    - SystemMessage: ignored
    - ResultMessage: "Result ended" + cost if available
    """
    if isinstance(msg, UserMessage):
        for block in msg.content:
            if isinstance(block, TextBlock):
                print(f"User: {block.text}")
    elif isinstance(msg, AssistantMessage):
        for block in msg.content:
            if isinstance(block, TextBlock):
                print(f"Claude: {block.text}")
            if isinstance(block, ToolUseBlock):
                print(f"🔨 Using tool: {block.name}")
    elif isinstance(msg, SystemMessage):
        # Ignore system messages
        pass
    elif isinstance(msg, ResultMessage):
        print("Result ended")


async def example_basic_streaming(prompt):
    options = ClaudeAgentOptions(
        system_prompt={
            "type": "preset",
            "preset": "claude_code",  # Use Claude Code's system prompt
        },
        setting_sources=["project"],  # Required to load CLAUDE.md from project
        allowed_tools=["Skill", "Read", "Grep", "Glob", "Bash", "WebFetch", "WebSearch"] 
    )

    async with ClaudeSDKClient(options=options) as client:
        await client.query(prompt)

        while True:
            # Receive complete response using the helper method
            async for msg in client.receive_response():
                display_message(msg)
            
            user_input = input(f"\nYou: ")

            if user_input.lower() == 'q':
                break
            
            # Send message - Claude remembers all previous messages in this session
            await client.query(user_input)


async def main():
    # 接受第一个命令行参数作为 prompt，如果没有则使用 _prompt3
    prompt = sys.argv[1] if len(sys.argv) > 1 else _prompt3
    await example_basic_streaming(prompt)

if __name__ == "__main__":
    anyio.run(main)
