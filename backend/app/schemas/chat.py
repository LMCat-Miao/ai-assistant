"""
聊天相关的数据模型。

职责：
1. 定义前端发送给后端的数据结构
2. 让 FastAPI / Pydantic 自动校验请求参数
"""

from typing import Literal

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    """单条聊天消息的结构（历史兼容 / 文档用）。"""

    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    """
    流式聊天请求。

    前端只提交当前会话 ID 和当前这句话，
    历史消息由后端根据 conversation_id 从数据库读取。
    """

    conversation_id: int = Field(..., gt=0, description="会话 ID")
    message: str = Field(..., min_length=1, description="当前用户消息")
