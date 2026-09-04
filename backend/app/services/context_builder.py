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
    构建最终发送给大模型的上下文。

    包含：
    1. System Prompt
    2. Chat History
    3. Current Question

    同时根据 Token Budget 自动裁剪历史消息。
    """

    system_message: ChatMessage = {
        "role": "system",
        "content": SYSTEM_PROMPT,
    }

    full_messages: list[ChatMessage] = [
        system_message,
        *messages,
    ]

    return trim_messages_by_tokens(
        full_messages,
        max_tokens=MAX_INPUT_TOKENS,
    )