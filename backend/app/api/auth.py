from fastapi import APIRouter
from pydantic import BaseModel
from app.core.security import create_access_token

router = APIRouter(
    prefix="/api/auth",
    tags=["认证"]
)


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(data: LoginRequest):

    if data.username == "admin" and data.password == "123456":

        access_token = create_access_token({
            "sub": "1",
            "username": data.username
        })

        return {
            "code": 200,
            "message": "登录成功",
            "data": {
                "access_token": access_token,
                "token_type": "bearer"
            }
        }

    return {
        "code": 401,
        "message": "用户名或密码错误"
    }