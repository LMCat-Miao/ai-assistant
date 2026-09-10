from fastapi import APIRouter, Depends,HTTPException
from app.api.dependencies import get_current_user
from app.repositories.conversation_repository import (
    create_conversation,get_conversation,get_conversations_by_user)
from app.repositories.message_reponsitory import(
    get_messages_by_conversation
)
router = APIRouter(
    prefix="/conversations",
    tags=["会话管理"],
)
@router.post("/")
def create_new_conversation(
    current_user: dict = Depends(get_current_user),
):
    """
    创建一个新的会话。
    """
    user_id = int(current_user["user_id"])
    conversation_id = create_conversation(
        user_id=user_id,
        title="新会话",
    )
    return {
        "code":200,
        "message":"创建会话成功",
        "data":{
            "conversation_id": conversation_id,
            "title": "新会话"
        }
    }
@router.get("/{conversation_id}/messages")
def get_conversation_messages(
    conversation_id: int,
    current_user: dict = Depends(get_current_user),
):
    """
    获取当前用户某个会话的全部消息。
    """

    user_id = int(current_user["user_id"])

    # 第一步：确认这个会话属于当前用户
    conversation = get_conversation(
        conversation_id=conversation_id,
        user_id=user_id,
    )

    if conversation is None:
        raise HTTPException(
            status_code=404,
            detail="会话不存在",
        )

    # 第二步：获取这个会话的消息
    messages = get_messages_by_conversation(
        conversation_id=conversation_id,
    )

    return {
        "code": 200,
        "message": "获取消息成功",
        "data": messages,
    }
@router.get("")
def get_user_conversations(
    current_user: dict = Depends(get_current_user),
):
    """
    获取当前登录用户的全部会话。
    """

    user_id = int(current_user["user_id"])

    conversations = get_conversations_by_user(
        user_id=user_id,
    )

    return {
        "code": 200,
        "message": "获取会话列表成功",
        "data": conversations,
    }