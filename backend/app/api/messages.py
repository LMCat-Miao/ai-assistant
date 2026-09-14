from fastapi import APIRouter

from app.repositories.message_reponsitory import create_message
from app.schemas.message import MessageCreate


router = APIRouter()


@router.post("/api/messages")
def create_message_api(
    data: MessageCreate,
):
    """
    创建一条聊天消息。
    """

    message_id = create_message(
        conversation_id=data.conversation_id,
        role=data.role,
        content=data.content,
    )

    return {
        "message_id": message_id,
    }