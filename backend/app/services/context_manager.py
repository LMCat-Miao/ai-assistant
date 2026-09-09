from typing import Literal, TypedDict

from app.services.tokenizer_service import count_chat_tokens


class ChatMessage(TypedDict):
    """
    AI 对话消息的数据结构。
    """

    role: Literal["system", "user", "assistant"]
    content: str


# ============================================================
# Token Budget 配置
# ============================================================

# 为了方便测试，当前故意设置得比较小。
# 以后接入真实模型时，需要根据模型实际上下文窗口调整。
MODEL_CONTEXT_WINDOW = 200

# 给 AI 输出预留的 Token
MAX_OUTPUT_TOKENS = 50

# 安全余量
SAFETY_MARGIN = 10

# 真正允许输入的 Token 数量
MAX_INPUT_TOKENS = (
    MODEL_CONTEXT_WINDOW
    - MAX_OUTPUT_TOKENS
    - SAFETY_MARGIN
)


# ============================================================
# Token 计算
# ============================================================

def calculate_chat_tokens(
    messages: list[ChatMessage],
) -> int:
    """
    计算一组聊天消息经过 Chat Template 后的 Token 数量。
    """

    return count_chat_tokens(messages)

def truncate_message_to_budget(
    system_messages: list[ChatMessage],
    message: ChatMessage,
    max_tokens: int,
) -> ChatMessage:
    """
    当当前用户消息本身超过 Token Budget 时，
    对当前消息进行 Token 级别的截断。

    使用二分搜索寻找：
    在 Token Budget 内能够保留的最大字符长度。
    """

    content = message["content"]

    # --------------------------------------------------------
    # 先判断完整消息是否已经满足 Budget
    # --------------------------------------------------------

    test_messages = [
        *system_messages,
        message,
    ]

    if calculate_chat_tokens(test_messages) <= max_tokens:
        return message

    # --------------------------------------------------------
    # 计算：
    #
    # system message 本身占用了多少 Token
    # --------------------------------------------------------

    system_tokens = calculate_chat_tokens(
        system_messages
    )

    # --------------------------------------------------------
    # 如果 system prompt 自己就超过 Budget
    # --------------------------------------------------------

    if system_tokens >= max_tokens:
        print(
            "❌ System Prompt 本身已经超过 Token Budget"
        )

        return {
            **message,
            "content": "",
        }

    # --------------------------------------------------------
    # 二分搜索
    #
    # 寻找：
    #
    # 最大的 content 字符长度
    #
    # 使：
    #
    # system + content <= max_tokens
    # --------------------------------------------------------

    left = 0
    right = len(content)

    best_length = 0

    while left <= right:

        mid = (left + right) // 2

        candidate_message: ChatMessage = {
            "role": message["role"],
            "content": content[:mid],
        }

        candidate_messages = [
            *system_messages,
            candidate_message,
        ]

        current_tokens = calculate_chat_tokens(
            candidate_messages
        )

        if current_tokens <= max_tokens:

            # 当前长度可以接受
            best_length = mid

            # 尝试保留更多内容
            left = mid + 1

        else:

            # 当前长度太长
            right = mid - 1

    # --------------------------------------------------------
    # 得到最终文本
    # --------------------------------------------------------

    truncated_content = content[:best_length]

    return {
        "role": message["role"],
        "content": truncated_content,
    }
# ============================================================
# 历史消息裁剪
# ============================================================

def trim_messages_by_budget(
    messages: list[ChatMessage],
    max_tokens: int,
) -> list[ChatMessage]:
    """
    根据 Token Budget 裁剪聊天历史。

    裁剪规则：

    1. system message 永远保留
    2. 当前用户问题尽量保留
    3. 历史按照 user + assistant 一轮一轮删除
    4. 每删除一轮重新计算 Token
    5. 尽可能保留最新的聊天历史
    """

    if not messages:
        return []

    # --------------------------------------------------------
    # 第一步：复制列表
    #
    # 防止直接修改调用方传进来的 messages
    # --------------------------------------------------------

    messages = messages.copy()

    # --------------------------------------------------------
    # 第二步：拆分 system 和普通聊天消息
    # --------------------------------------------------------

    system_messages = [
        message
        for message in messages
        if message["role"] == "system"
    ]

    conversation_messages = [
        message
        for message in messages
        if message["role"] != "system"
    ]

    # 没有普通聊天消息
    if not conversation_messages:
        return system_messages

    # --------------------------------------------------------
    # 第三步：最后一条消息认为是当前消息
    # --------------------------------------------------------

    current_message = conversation_messages[-1]

    # 前面的全部属于历史
    history_messages = conversation_messages[:-1]

    # --------------------------------------------------------
    # 第四步：第一次尝试
    #
    # system
    # +
    # 所有历史
    # +
    # 当前消息
    # --------------------------------------------------------

    result = [
        *system_messages,
        *history_messages,
        current_message,
    ]

    current_tokens = calculate_chat_tokens(result)

    print("\n" + "-" * 60)
    print("Context 裁剪检查")
    print("-" * 60)
    print(f"当前 Token：{current_tokens}")
    print(f"Token Budget：{max_tokens}")

    # --------------------------------------------------------
    # 第五步：没有超过 Budget
    # --------------------------------------------------------

    if current_tokens <= max_tokens:
        print("✅ 没有超过 Token Budget")

        return result

    # --------------------------------------------------------
    # 第六步：开始删除历史
    # --------------------------------------------------------

    print("⚠️ 超过 Token Budget，开始裁剪历史")

    while history_messages:

        # 删除最早的一条历史消息
        history_messages.pop(0)

        # ----------------------------------------------------
        # 防止留下孤立 assistant
        #
        # 例如：
        #
        # user
        # assistant
        # user
        #
        # 删除第一个 user 后：
        #
        # assistant
        # user
        #
        # 此时需要把最前面的 assistant 一起删除
        # ----------------------------------------------------

        if (
            history_messages
            and history_messages[0]["role"] == "assistant"
        ):
            history_messages.pop(0)

        # ----------------------------------------------------
        # 重新构建 Context
        # ----------------------------------------------------

        result = [
            *system_messages,
            *history_messages,
            current_message,
        ]

        current_tokens = calculate_chat_tokens(result)

        print(
            f"裁剪后 Token：{current_tokens}"
        )

        # ----------------------------------------------------
        # Token 已经满足要求
        # ----------------------------------------------------

        if current_tokens <= max_tokens:
            print("✅ 裁剪完成")

            return result


# 第七步：
#
# 历史全部删除之后仍然超限
#
# 说明当前用户消息本身过长
# --------------------------------------------------------

    print(
    "⚠️ 历史已经全部删除，当前消息仍然超过 Token Budget"
)

    print(
    "✂️ 开始对当前用户消息进行 Token 截断"
)

    current_message = truncate_message_to_budget(
        system_messages=system_messages,
        message=current_message,
        max_tokens=max_tokens,
    )

    result = [
        *system_messages,
        current_message,
    ]

    current_tokens = calculate_chat_tokens(result)

    print(
        f"✂️ 当前消息截断后 Token：{current_tokens}"
    )

    if current_tokens <= max_tokens:
        print("✅ 当前用户消息截断完成")
    else:
        print(
        "❌ 截断后仍然超过 Token Budget"
    )

    return result