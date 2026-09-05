from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.api.dependencies import get_current_user
from app.schemas.chat import ChatRequest
from app.services.ai_service import chat_with_ai_stream
from app.services.context_builder import build_context

router = APIRouter(
    prefix="/api/chat",
    tags=["AI聊天"],
)


@router.post("/stream")
def chat_stream(
    data: ChatRequest,
    current_user: dict = Depends(get_current_user),
):
    messages = [
        message.model_dump()
        for message in data.messages
    ]

    context = build_context(messages)

    print("\n" + "=" * 60)
    print("最终发送给 AI 的 Context")
    print("=" * 60)

    for message in context:
        print(
            f"{message['role']}: "
            f"{message['content']}"
        )

    print("=" * 60)

    return StreamingResponse(
        chat_with_ai_stream(context),
        media_type="text/plain",
    )