from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.auth import router as auth_router
from app.api.user import router as user_router
from app.api.chat import router as chat_router
app = FastAPI(
    title="AI Learning Assistant ",
)

app.include_router(auth_router)
app.include_router(user_router)
app.include_router(chat_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth_router)

@app.get("/")
def root():
    return {
        "message": "AI Learning Assistant Backend"
    }
