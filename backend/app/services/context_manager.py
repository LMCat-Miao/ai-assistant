from typing import TypedDict

from app.services.tokenizer_service import count_tokens


class ChatMessage(TypedDict):
    role: str
    content: str


def calculate_messages_tokens(
    messages: list[ChatMessage],
) -> int:
    """
    计算消息内容的 Token 数量。
    """

    total_tokens = 0

    for message in messages:
        total_tokens += count_tokens(
            message["content"]
        )

    return total_tokens


def trim_messages_by_tokens(
    messages: list[ChatMessage],
    max_tokens: int,
) -> list[ChatMessage]:
    """
    根据 Token 预算裁剪历史消息。

    当消息总 Token 数超过 max_tokens 时，
    从最旧的消息开始删除。
    """

    messages = messages.copy()

    while (
        messages
        and calculate_messages_tokens(messages) > max_tokens
    ):
        messages.pop(0)

    return messages