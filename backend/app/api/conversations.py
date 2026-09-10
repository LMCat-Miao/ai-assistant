from fastapi import APIRouter, Depends
from app.api.dependencies import get_current_user
from app.respositories.conversation_repository import (
    create_conversation)
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
    