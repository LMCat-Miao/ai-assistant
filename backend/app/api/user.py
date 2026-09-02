from fastapi import APIRouter, Depends

from app.api.dependencies import get_current_user


router = APIRouter(
    prefix="/api/user",
    tags=["用户"]
)


@router.get("/me")
def get_me(
    current_user: dict = Depends(get_current_user)
):
    return {
        "code": 200,
        "message": "获取用户信息成功",
        "data": current_user
    }