from typing import Literal, TypedDict

from app.services.tokenizer_service import count_tokens


# ==============================
# 类型定义
# ==============================

class ChatMessage(TypedDict):
    """
    一条聊天消息。

    role:
        system / user / assistant

    content:
        消息内容
    """

    role: Literal["system", "user", "assistant"]
    content: str


# ==============================
# Context Budget
# ==============================

MODEL_CONTEXT_WINDOW = 8000

MAX_OUTPUT_TOKENS = 2000

MAX_INPUT_TOKENS = (
    MODEL_CONTEXT_WINDOW
    - MAX_OUTPUT_TOKENS
)


# ==============================
# Token 计算
# ==============================

def calculate_messages_tokens(
    messages: list[ChatMessage],
) -> int:
    """
    计算消息列表的 Token 数量。
    """

    total_tokens = 0

    for message in messages:
        total_tokens += count_tokens(
            message["content"]
        )

    return total_tokens


# ==============================
# 历史消息裁剪
# ==============================

def trim_messages_by_tokens(
    messages: list[ChatMessage],
    max_tokens: int = MAX_INPUT_TOKENS,
) -> list[ChatMessage]:
    """
    根据 Token Budget 裁剪聊天历史。

    规则：

    1. System Prompt 永远保留
    2. 优先删除最早的历史消息
    3. 尽量保持 user + assistant 成对删除
    4. 当前用户问题尽量保留
    """

    messages = messages.copy()

    # ------------------------------
    # 分离 System Message
    # ------------------------------

    system_messages = [
        message
        for message in messages
        if message["role"] == "system"
    ]

    # ------------------------------
    # 获取普通对话
    # ------------------------------

    conversation_messages = [
        message
        for message in messages
        if message["role"] != "system"
    ]

    # ------------------------------
    # 判断 Token 是否超预算
    # ------------------------------

    while (
        conversation_messages
        and calculate_messages_tokens(
            system_messages
            + conversation_messages
        ) > max_tokens
    ):

        # 至少有两条消息时，
        # 优先删除最早的一轮 user + assistant
        if (
            len(conversation_messages) >= 3
            and conversation_messages[0]["role"] == "user"
            and conversation_messages[1]["role"] == "assistant"
        ):
            del conversation_messages[:2]

        else:
            # 如果无法组成完整的一轮，
            # 删除最早消息
            del conversation_messages[0]

    return system_messages + conversation_messages