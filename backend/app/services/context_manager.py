from typing import Literal, TypedDict

from app.services.tokenizer_service import count_chat_tokens, count_tokens


class ChatMessage(TypedDict):
    role: Literal["user", "assistant"]
    content: str


def calculate_messages_tokens(
    messages: list[ChatMessage],
) -> int:
    """
    计算消息内容的 Token 数量。
    """

    return count_chat_tokens(messages)


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