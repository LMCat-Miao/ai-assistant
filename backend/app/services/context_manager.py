from typing import Literal, TypedDict

from app.services.tokenizer_service import count_chat_tokens



class ChatMessage(TypedDict):
    role: Literal["system", "user", "assistant"]
    content: str

MODEL_CONTEXT_WINDOW = 8000
MAX_OUTPUT_TOKENS = 2000
MAX_INPUT_TOKENS = (MODEL_CONTEXT_WINDOW 
                    - MAX_OUTPUT_TOKENS)


def calculate_messages_tokens(
    messages: list[ChatMessage],
) -> int:
    """
    计算消息内容的 Token 数量。
    """

    return count_chat_tokens(messages)


def trim_messages_by_tokens(
    messages: list[ChatMessage],
    max_tokens: int = MAX_INPUT_TOKENS,
) -> list[ChatMessage]:
    
    """
    根据 Token 预算裁剪历史消息。

    当消息总 Token 数超过 max_tokens 时，
    从最旧的消息开始删除。
    """

    messages = messages.copy()
    system_messages =[
        message 
        for message in messages
        if(message["role"] == "system")
    ]
    conversation_messages = [
        message
        for message in messages
        if(message["role"] != "system")
    ]
    while(
        conversation_messages 
        and calculate_messages_tokens(
            system_messages + conversation_messages
        ) > max_tokens
    ):
        if(
            len(conversation_messages) > 2
            and conversation_messages[0]["role"] == "user"
            and conversation_messages[1]["role"] == "assistant"
        ):
            del conversation_messages[:2]
        else:
            conversation_messages.pop(0)
    return system_messages + conversation_messages