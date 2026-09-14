from collections.abc import Generator

from app.repositories.conversation_repository import get_conversation
from app.repositories.message_reponsitory import (
    create_message,
    get_messages_by_conversation,
)
from app.services.ai_service import chat_with_ai_stream
from app.services.context_builder import build_context


def stream_chat(
    conversation_id: int,
    user_id: int,
    message: str,
) -> Generator[str, None, None]:
    """
    执行一次完整的 AI 对话流程。

    流程：
    1. 验证会话归属
    2. 保存用户消息
    3. 查询历史消息
    4. 构建 AI Context
    5. 调用 AI 并流式返回
    6. 保存完整 AI 回复
    """

    # 1. 验证当前用户是否拥有这个会话
    conversation = get_conversation(
        conversation_id=conversation_id,
        user_id=user_id,
    )

    if conversation is None:
        raise ValueError("会话不存在")

    # 2. 保存用户当前发送的消息
    create_message(
        conversation_id=conversation_id,
        role="user",
        content=message,
    )

    # 3. 从数据库读取当前会话的完整历史
    history = get_messages_by_conversation(
        conversation_id=conversation_id,
    )

    # 4. 转换成 AI 所需要的消息格式
    messages = [
        {
            "role": item["role"],
            "content": item["content"],
        }
        for item in history
    ]

    # 5. 根据 Token 预算构建最终 Context
    context = build_context(messages)

    # 6. 调用 AI，并保存完整的 assistant 回复
    assistant_content = ""

    for chunk in chat_with_ai_stream(context):
        # 累积完整回答
        assistant_content += chunk

        # 将当前 chunk 立即返回给前端
        yield chunk

    # 7. AI 完整回答生成后，再一次性保存到数据库
    create_message(
        conversation_id=conversation_id,
        role="assistant",
        content=assistant_content,
    )