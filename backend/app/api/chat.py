from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.api.dependencies import get_current_user
from app.schemas.chat import ChatRequest
from app.services.chat_service import stream_chat


router = APIRouter(
    prefix="/api/chat",
    tags=["AI 对话"],
)


@router.post("/stream")
def chat_stream(
    data: ChatRequest,
    current_user: dict = Depends(get_current_user),
):
    user_id = int(current_user["user_id"])

    return StreamingResponse(
        stream_chat(
            conversation_id=data.conversation_id,
            user_id=user_id,
            message=data.message,
        ),
        media_type="text/plain",
    )