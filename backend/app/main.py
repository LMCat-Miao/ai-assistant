from contextlib import asynccontextmanager

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时检查 MySQL，关闭时释放连接池。"""

    try:
        init_database()
        yield
    finally:
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
