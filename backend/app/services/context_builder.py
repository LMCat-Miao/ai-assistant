from app.prompts.system import SYSTEM_PROMPT

from app.services.context_manager import (
    ChatMessage,
    MAX_INPUT_TOKENS,
    trim_messages_by_budget,
)


def build_context(
    messages: list[ChatMessage],
) -> list[ChatMessage]:

    system_message: ChatMessage = {
        "role": "system",
        "content": SYSTEM_PROMPT,
    }

    full_messages = [
        system_message,
        *messages,
    ]

    return trim_messages_by_budget(
        full_messages,
        max_tokens=MAX_INPUT_TOKENS,
    )