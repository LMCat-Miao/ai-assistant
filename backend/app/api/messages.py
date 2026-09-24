"""
消息 API。

创建消息前必须：
1. JWT 鉴权（get_current_user）
2. 校验 conversation_id 属于当前用户
"""

from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import get_current_user
from app.repositories.conversation_repository import get_conversation
from app.repositories.message_reponsitory import create_message
from app.schemas.message import MessageCreate


router = APIRouter()


@router.post("/api/messages")
def create_message_api(
    data: MessageCreate,
    current_user: dict = Depends(get_current_user),
):
    """
    创建一条聊天消息。

    仅允许向「当前登录用户拥有的会话」写入。
    用户身份来自 Token，不信任请求体中的任何用户标识。
    """

    user_id = int(current_user["user_id"])

    # 归属校验：不存在或不属于当前用户 → 统一 404，且不落库
    conversation = get_conversation(
        conversation_id=data.conversation_id,
        user_id=user_id,
    )

    if conversation is None:
        raise HTTPException(
            status_code=404,
            detail="会话不存在",
        )

    message_id = create_message(
        conversation_id=data.conversation_id,
        role=data.role,
        content=data.content,
    )

    return {
        "message_id": message_id,
    }
