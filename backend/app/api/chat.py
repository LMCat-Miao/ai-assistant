from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.api.dependencies import get_current_user
from app.schemas.chat import ChatRequest
from app.services.ai_service import chat_with_ai_stream


router = APIRouter(
    prefix="/api/chat",
    tags=["AI聊天"],
)


@router.post("/stream")
def chat(
    data: ChatRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    AI 聊天接口。

    当前版本：
    - 需要登录
    - 接收用户消息
    - 调用 AI
    - 返回流式回答
    """

    return StreamingResponse(
        chat_with_ai_stream(data.message),
        media_type="text/plain"
    )