from fastapi import APIRouter
from pydantic import BaseModel

from app.core.password import verify_password
from app.core.security import create_access_token
from app.repositories.user_repository import get_user_by_username

router = APIRouter(
    prefix="/api/auth",
    tags=["认证"],
)


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(data: LoginRequest):
    """
    从 users 表校验用户名与密码，成功后签发 JWT。

    用户不存在与密码错误返回同一文案，避免枚举账号。
    """

    user = get_user_by_username(data.username.strip())

    if user is None or not verify_password(
        data.password,
        user["password_hash"],
    ):
        return {
            "code": 401,
            "message": "用户名或密码错误",
        }

    access_token = create_access_token(
        {
            # sub 使用数据库真实用户 ID，保持字符串以兼容现有 get_current_user
            "sub": str(user["id"]),
            "username": user["username"],
        }
    )

    return {
        "code": 200,
        "message": "登录成功",
        "data": {
            "access_token": access_token,
            "token_type": "bearer",
        },
    }
