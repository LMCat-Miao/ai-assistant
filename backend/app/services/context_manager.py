from typing import Literal, TypedDict

from app.services.tokenizer_service import count_chat_tokens


# ============================================================
# Message 类型
# ============================================================

class ChatMessage(TypedDict):
    role: Literal[
        "system",
        "user",
        "assistant",
    ]

    content: str


# ============================================================
# Token Budget
# ============================================================

MODEL_CONTEXT_WINDOW = 200

MAX_OUTPUT_TOKENS = 50

SAFETY_MARGIN = 10

MAX_INPUT_TOKENS = (
    MODEL_CONTEXT_WINDOW
    - MAX_OUTPUT_TOKENS
    - SAFETY_MARGIN
)


# ============================================================
# 计算完整 Chat Context Token
# ============================================================

def calculate_chat_tokens(
    messages: list[ChatMessage],
) -> int:
    """
    计算完整 messages 经过 Chat Template
    之后的 Token 数量。
    """

    return count_chat_tokens(messages)


# ============================================================
# 根据 Token Budget 裁剪 Context
# ============================================================

def trim_messages_by_budget(
    messages: list[ChatMessage],
    max_tokens: int,
) -> list[ChatMessage]:
    """
    根据 Token Budget 裁剪历史消息。

    规则：

    1. system 消息永远保留
    2. 当前用户消息尽量保留
    3. 历史消息按照 user + assistant 一轮删除
    4. 每删除一轮后重新计算 Token
    """

    # --------------------------------------------------------
    # 复制一份消息
    #
    # 防止直接修改外部 messages
    # --------------------------------------------------------

    messages = messages.copy()

    # --------------------------------------------------------
    # 如果没有消息，直接返回
    # --------------------------------------------------------

    if not messages:
        return []

    # --------------------------------------------------------
    # 找到 system message
    # --------------------------------------------------------

    system_messages = [
        message
        for message in messages
        if message["role"] == "system"
    ]

    # --------------------------------------------------------
    # 找到普通对话消息
    # --------------------------------------------------------

    conversation_messages = [
        message
        for message in messages
        if message["role"] != "system"
    ]

    # --------------------------------------------------------
    # 当前用户消息
    #
    # 正常情况下最后一条就是当前问题
    # --------------------------------------------------------

    current_message = None

    if conversation_messages:
        current_message = conversation_messages[-1]

    # --------------------------------------------------------
    # 历史消息
    #
    # 当前问题不参与删除
    # --------------------------------------------------------

    history_messages = conversation_messages[:-1]

    # --------------------------------------------------------
    # 重新组装 Context
    # --------------------------------------------------------

    result = [
        *system_messages,
        *history_messages,
    ]

    if current_message:
        result.append(current_message)

    # --------------------------------------------------------
    # 如果当前 Token 没超过预算
    # 直接返回
    # --------------------------------------------------------

    if calculate_chat_tokens(result) <= max_tokens:
        return result

    # --------------------------------------------------------
    # 开始删除历史消息
    #
    # 每次删除 user + assistant 一轮
    # --------------------------------------------------------

    while history_messages:

        # ====================================================
        # 找到第一轮历史对话
        # ====================================================

        remove_count = 0

        # ----------------------------------------------------
        # 第一个应该是 user
        # ----------------------------------------------------

        if history_messages:
            history_messages.pop(0)
            remove_count += 1

        # ----------------------------------------------------
        # 如果后面紧跟 assistant
        # 一起删除
        # ----------------------------------------------------

        if (
            history_messages
            and history_messages[0]["role"] == "assistant"
        ):
            history_messages.pop(0)
            remove_count += 1

        # ----------------------------------------------------
        # 重新构建 Context
        # ----------------------------------------------------

        result = [
            *system_messages,
            *history_messages,
        ]

        if current_message:
            result.append(current_message)

        # ----------------------------------------------------
        # 重新计算 Token
        # ----------------------------------------------------

        current_tokens = calculate_chat_tokens(
            result
        )

        # ----------------------------------------------------
        # 如果已经进入预算
        # 停止删除
        # ----------------------------------------------------

        if current_tokens <= max_tokens:
            break

    return result