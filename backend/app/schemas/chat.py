"""
聊天相关的数据模型。

职责：
1. 定义前端发送给后端的数据结构
2. 让 FastAPI 自动进行请求参数校验
"""

from pydantic import BaseModel


class ChatMessage(BaseModel):
    role: str
    content: str
class ChatRequest(BaseModel):
    messages: list[ChatMessage]