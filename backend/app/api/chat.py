from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.api.dependencies import get_current_user
from app.schemas.chat import ChatRequest
from app.services.ai_service import chat_with_ai_stream
from app.services.context_builder import build_context

from app.repositories.conversation_repository import get_conversation
from app.repositories.message_reponsitory import (
    create_message,
    get_messages_by_conversation,
)


router = APIRouter(
    prefix="/api/chat",
    tags=["AI 对话"],
)


@router.post("/stream")
def chat_stream(
    data: ChatRequest,
    current_user: dict = Depends(get_current_user),
):
    # ============================================================
    # 1. 获取当前登录用户 ID
    # ============================================================

    user_id = int(current_user["user_id"])

    # ============================================================
    # 2. 检查会话是否存在，并且属于当前用户
    # ============================================================

    conversation = get_conversation(
        conversation_id=data.conversation_id,
        user_id=user_id,
    )

    if conversation is None:
        raise HTTPException(
            status_code=404,
            detail="会话不存在",
        )

    # ============================================================
    # 3. 保存用户刚刚发送的消息
    # ============================================================

    create_message(
        conversation_id=data.conversation_id,
        role="user",
        content=data.message,
    )

    # ============================================================
    # 4. 从数据库查询这个会话的历史消息
    # ============================================================

    db_messages = get_messages_by_conversation(
        conversation_id=data.conversation_id,
    )

    # ============================================================
    # 5. 转换成 Context Manager 需要的格式
    # ============================================================

    messages = [
        {
            "role": message["role"],
            "content": message["content"],
        }
        for message in db_messages
    ]

    # ============================================================
    # 6. 构建最终发送给 AI 的 Context
    # ============================================================

    context = build_context(messages)

    # ============================================================
    # 7. 定义 AI 流式生成器
    # ============================================================

    def generate():
        assistant_content = ""

        try:
            for chunk in chat_with_ai_stream(context):
                # ------------------------------------------------
                # 累积 AI 输出
                # ------------------------------------------------

                assistant_content += chunk

                # ------------------------------------------------
                # 立即把 chunk 返回给前端
                # ------------------------------------------------

                yield chunk

            # ====================================================
            # 8. AI 完整回答结束后，再保存 assistant 消息
            # ====================================================

            create_message(
                conversation_id=data.conversation_id,
                role="assistant",
                content=assistant_content,
            )

        except Exception:
            # 第一版暂时不保存异常情况下的半截回答
            raise

    # ============================================================
    # 9. 返回 StreamingResponse
    # ============================================================

    return StreamingResponse(
        generate(),
        media_type="text/plain",
    )