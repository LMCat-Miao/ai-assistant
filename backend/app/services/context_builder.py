from app.prompts.system import SYSTEM_PROMPT

from app.services.context_manager import (
    ChatMessage,
    trim_messages_by_tokens,
    MAX_INPUT_TOKENS,
)


def build_context(
    messages: list[ChatMessage],
) -> list[ChatMessage]:
    """
    构建发送给 AI 的最终 Context。

    Context 包含：

    1. System Prompt
    2. Chat History
    3. Current Question

    同时进行 Token Budget 控制。
    """

    # 1. 创建 System Message
    system_message: ChatMessage = {
        "role": "system",
        "content": SYSTEM_PROMPT,
    }

    # 2. 合并 System Prompt + 用户聊天记录
    full_messages: list[ChatMessage] = [
        system_message,
        *messages,
    ]

    # 3. 根据 Token Budget 裁剪
    context = trim_messages_by_tokens(
        full_messages,
        max_tokens=MAX_INPUT_TOKENS,
    )

    return context