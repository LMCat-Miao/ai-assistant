"""
聊天 API 路由。

职责：
1. 接收前端请求并校验参数（ChatRequest）
2. 通过 JWT 依赖获取当前用户
3. 同步调用 chat_service 完成准备阶段
4. 将业务异常转换成 HTTP 错误
5. 返回 StreamingResponse 进行流式输出
   （若本次生成了会话标题，通过响应头带回，不破坏纯文本流）
"""

from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from app.api.dependencies import get_current_user
from app.schemas.chat import ChatRequest
from app.services.chat_service import (
    ChatGenerationError,
    ChatPreparationError,
    ConversationNotFoundError,
    generate_assistant_reply,
    prepare_chat_context,
)


router = APIRouter(
    prefix="/api/chat",
    tags=["AI 对话"],
)

# 供前端读取新标题；中文需 URL 编码后放入 Header
TITLE_HEADER = "X-Conversation-Title"


@router.post("/stream")
def chat_stream(
    data: ChatRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    流式聊天接口。

    请求体：
    {
      "conversation_id": 1,
      "message": "请解释一下 JavaScript 的闭包"
    }
    """

    user_id = int(current_user["user_id"])

    try:
        prepared = prepare_chat_context(
            conversation_id=data.conversation_id,
            user_id=user_id,
            message=data.message,
        )
    except ConversationNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ChatPreparationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    response_headers: dict[str, str] = {}
    if prepared.generated_title:
        # 百分号编码，避免中文标题无法放入 HTTP Header
        response_headers[TITLE_HEADER] = quote(
            prepared.generated_title,
            safe="",
        )

    def event_stream():
        try:
            yield from generate_assistant_reply(
                conversation_id=data.conversation_id,
                context=prepared.context,
            )
        except ChatGenerationError as exc:
            print(f"AI 流式生成失败: {exc}")
            return

    return StreamingResponse(
        event_stream(),
        media_type="text/plain; charset=utf-8",
        headers=response_headers,
    )
