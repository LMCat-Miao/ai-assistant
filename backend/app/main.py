from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth import router as auth_router
from app.api.user import router as user_router
from app.api.chat import router as chat_router
from app.api.conversations import router as conversations_router
from app.api.messages import router as messages_router
from app.api.knowledge import router as knowledge_router
from app.database import dispose_engine
from app.database_init import init_database
from app.redis_client import close_redis, init_redis


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：检查 MySQL；尽量连接 Redis；关闭时释放 Redis 与 MySQL 连接池。"""

    try:
        init_database()
        # Redis 为可选基础设施：失败只记日志，不阻断 MySQL / 登录 / 聊天 / RAG
        if not init_redis():
            logger.warning(
                "Redis 不可用：邮箱验证码等依赖 Redis 的功能将暂不可用；"
                "其余业务照常运行"
            )
        yield
    finally:
        try:
            close_redis()
        except Exception as exc:  # noqa: BLE001 — 不得阻止 MySQL Engine 释放
            logger.warning("close_redis() 异常（已忽略，继续释放 MySQL）：%s", exc)
        dispose_engine()


app = FastAPI(
    title="AI Learning Assistant ",
    lifespan=lifespan,
)

app.include_router(auth_router)
app.include_router(user_router)
app.include_router(chat_router)
app.include_router(conversations_router)
app.include_router(messages_router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # 允许前端读取流式响应里的会话标题与知识库引用头
    expose_headers=[
        "X-Conversation-Title",
        "X-Knowledge-Citations",
        "X-Knowledge-Status",
    ],
)
app.include_router(knowledge_router)


@app.get("/")
def root():
    return {
        "message": "AI Learning Assistant Backend"
    }
