"""
聊天业务服务。

职责：
1. 校验会话归属
2. 保存用户消息、读取历史
3. 首条消息时自动生成会话标题（截断，不调大模型）
4. 构建模型上下文
5. 驱动流式 AI 生成，并在成功后保存完整回复
"""

from collections.abc import Generator
from typing import NamedTuple

from app.repositories.conversation_repository import (
    get_conversation,
    update_conversation_title,
)
from app.repositories.message_reponsitory import (
    create_message,
    get_messages_by_conversation,
)
from app.services.ai_service import chat_with_ai_stream
from app.services.context_builder import build_context
from app.services.context_manager import ChatMessage


class ConversationNotFoundError(Exception):
    """会话不存在，或不属于当前用户。"""


class ChatPreparationError(Exception):
    """聊天准备阶段失败（保存消息、构建上下文等）。"""


class ChatGenerationError(Exception):
    """AI 流式生成失败。"""


# 与前端创建会话时的默认标题保持一致
DEFAULT_CONVERSATION_TITLE = "新会话"

# 侧栏展示用的标题最大字符数（按 Unicode 字符计）
MAX_TITLE_LENGTH = 30


class PrepareChatResult(NamedTuple):
    """准备阶段的返回值。"""

    context: list[ChatMessage]
    # 本次若新生成了标题则返回，否则为 None（供响应头带回前端）
    generated_title: str | None


def is_default_title(title: str | None) -> bool:
    """判断是否仍为占位标题，允许再次自动生成。"""

    text = (title or "").strip()
    return text == "" or text == DEFAULT_CONVERSATION_TITLE


def build_title_from_message(message: str) -> str | None:
    """
    用首条用户消息生成简洁标题。

    - 去掉首尾空白，合并多余空白/换行
    - 按字符截断，避免侧栏被长文本撑开
    - 无有效内容时返回 None
    """

    normalized = " ".join(message.strip().split())
    if not normalized:
        return None

    if len(normalized) <= MAX_TITLE_LENGTH:
        return normalized

    return normalized[:MAX_TITLE_LENGTH].rstrip() + "…"


def maybe_update_conversation_title(
    conversation_id: int,
    user_id: int,
    current_title: str | None,
    user_message: str,
    user_message_count_before: int,
) -> str | None:
    """
    在「默认标题 + 本条是第一条用户消息」时更新标题。

    标题生成失败只记录日志，不影响聊天主流程。
    """

    if not is_default_title(current_title):
        return None

    # 保存本条之前已有用户消息，说明不是第一条，不再覆盖
    if user_message_count_before > 0:
        return None

    new_title = build_title_from_message(user_message)
    if new_title is None:
        return None

    try:
        updated = update_conversation_title(
            conversation_id=conversation_id,
            user_id=user_id,
            title=new_title,
        )
        if updated:
            return new_title
    except Exception as exc:
        # 标题失败不得打断流式聊天
        print(f"更新会话标题失败: {exc}")

    return None


def prepare_chat_context(
    conversation_id: int,
    user_id: int,
    message: str,
) -> PrepareChatResult:
    """
    同步准备一次聊天所需的模型上下文。

    在创建 StreamingResponse 之前调用。
    执行顺序：
    1. 校验会话属于当前用户
    2. 保存当前用户消息
    3. 必要时根据首条消息生成并持久化标题
    4. 读取历史并构建 Context
    """

    content = message.strip()
    if not content:
        raise ChatPreparationError("消息内容不能为空")

    conversation = get_conversation(
        conversation_id=conversation_id,
        user_id=user_id,
    )

    if conversation is None:
        raise ConversationNotFoundError("会话不存在")

    # 统计「保存本条之前」的用户消息数，用于判断是否首条
    try:
        history_before = get_messages_by_conversation(
            conversation_id=conversation_id,
        )
    except Exception as exc:
        raise ChatPreparationError("读取会话历史失败") from exc

    user_message_count_before = sum(
        1 for item in history_before if item.get("role") == "user"
    )

    # 先持久化用户消息；失败则不会生成标题
    try:
        create_message(
            conversation_id=conversation_id,
            role="user",
            content=content,
        )
    except Exception as exc:
        raise ChatPreparationError("保存用户消息失败") from exc

    # 用户消息已成功入库后，再尝试生成标题
    generated_title = maybe_update_conversation_title(
        conversation_id=conversation_id,
        user_id=user_id,
        current_title=conversation.get("title"),
        user_message=content,
        user_message_count_before=user_message_count_before,
    )

    try:
        history = get_messages_by_conversation(
            conversation_id=conversation_id,
        )
    except Exception as exc:
        raise ChatPreparationError("读取会话历史失败") from exc

    messages: list[ChatMessage] = [
        {
            "role": item["role"],
            "content": item["content"],
        }
        for item in history
    ]

    try:
        context = build_context(messages)
    except Exception as exc:
        raise ChatPreparationError("构建对话上下文失败") from exc

    return PrepareChatResult(
        context=context,
        generated_title=generated_title,
    )


def generate_assistant_reply(
    conversation_id: int,
    context: list[ChatMessage],
) -> Generator[str, None, None]:
    """
    流式生成 AI 回复，并在「完整成功」后写入数据库。
    """

    assistant_content = ""
    completed = False

    try:
        for chunk in chat_with_ai_stream(context):
            assistant_content += chunk
            yield chunk

        completed = True

    except GeneratorExit:
        raise

    except Exception as exc:
        raise ChatGenerationError("AI 生成失败") from exc

    if completed and assistant_content:
        try:
            create_message(
                conversation_id=conversation_id,
                role="assistant",
                content=assistant_content,
            )
        except Exception as exc:
            raise ChatGenerationError("保存 AI 回复失败") from exc


def stream_chat(
    conversation_id: int,
    user_id: int,
    message: str,
) -> Generator[str, None, None]:
    """兼容入口：同步准备 + 流式生成。"""

    prepared = prepare_chat_context(
        conversation_id=conversation_id,
        user_id=user_id,
        message=message,
    )

    yield from generate_assistant_reply(
        conversation_id=conversation_id,
        context=prepared.context,
    )
