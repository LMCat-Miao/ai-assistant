from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.api.dependencies import get_current_user
from app.schemas.chat import ChatRequest
from app.services.ai_service import chat_with_ai_stream
from app.services.context_builder import build_context


router = APIRouter(
    prefix="/api/chat",
    tags=["AI 对话"],
)


@router.post("/stream")
def chat_stream(
    data: ChatRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    AI 流式聊天接口。

    请求流程：

    前端 messages
        ↓
    Pydantic 校验
        ↓
    转换成普通 dict
        ↓
    Context Builder
        ↓
    Token Budget 管理
        ↓
    AI
        ↓
    StreamingResponse
    """

    # ========================================================
    # 1. 将 Pydantic Message 转成普通 dict
    # ========================================================

    messages = [
        message.model_dump()
        for message in data.messages
    ]

    # ========================================================
    # 2. 构建最终 Context
    #
    # 这里会：
    #
    # - 加入 System Prompt
    # - 计算 Chat Template Token
    # - 检查 Token Budget
    # - 超出预算时删除旧对话
    # ========================================================

    context = build_context(
        messages
    )

    # ========================================================
    # 3. 开发阶段打印最终 Context
    #
    # 用来确认真正发送给 AI 的内容
    # ========================================================

    print("\n" + "=" * 60)
    print("最终发送给 AI 的 Context")
    print("=" * 60)

    for message in context:
        print(
            f"{message['role']}: "
            f"{message['content']}"
        )

    print("=" * 60)

    # ========================================================
    # 4. 调用 AI 流式生成
    # ========================================================

    return StreamingResponse(
        chat_with_ai_stream(context),
        media_type="text/plain",
    )