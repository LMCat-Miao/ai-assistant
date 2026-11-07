"""
认证 API：登录 + 邮箱验证码注册发码 / 注册。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter
from pydantic import BaseModel
from redis.exceptions import RedisError
from sqlalchemy.exc import IntegrityError

from app.core.password import hash_password, verify_password
from app.core.security import create_access_token
from app.repositories.user_repository import (
    create_user,
    get_user_by_email,
    get_user_by_username,
)
from app.schemas.auth import RegisterRequest, SendRegisterCodeRequest
from app.services.email_code_service import (
    CODE_TTL_SECONDS,
    CooldownActiveError,
    EmailCodeConfigError,
    RedisUnavailableError,
    VerifyStatus,
    cancel_code_issue,
    issue_code,
    verify_and_consume_code,
)
from app.services.email_service import (
    EmailSendError,
    EmailSMTPConfigError,
    send_register_code_email,
)


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/auth",
    tags=["认证"],
)

# 发码通用文案：已注册与新邮箱返回接近提示，降低枚举；真实故障仍返回明确错误
_SEND_CODE_GENERIC_MESSAGE = (
    "如果该邮箱可以注册，验证码将发送到该邮箱（请查收；有效期 5 分钟）"
)


class LoginRequest(BaseModel):
    username: str
    password: str


def _ok(message: str, data: dict | None = None, *, code: int = 200) -> dict:
    return {"code": code, "message": message, "data": data}


def _fail(code: int, message: str, data: dict | None = None) -> dict:
    return {"code": code, "message": message, "data": data}


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


@router.post("/email/send-code")
def send_register_code(data: SendRegisterCodeRequest):
    """
    发送注册邮箱验证码。

    已注册邮箱不发信，但仍返回通用成功提示（防枚举）。
    Redis / SMTP 真实故障不伪装成发送成功。
    """

    email = str(data.email).strip().lower()

    try:
        if get_user_by_email(email) is not None:
            # 不发码、不写 Redis，响应与可注册路径接近
            logger.info("注册发码：邮箱已存在，跳过发送 email=%s", email)
            return _ok(
                _SEND_CODE_GENERIC_MESSAGE,
                {"expires_in": CODE_TTL_SECONDS},
            )

        issued = issue_code(email)
        try:
            send_register_code_email(issued.email, issued.code)
        except (EmailSendError, EmailSMTPConfigError) as exc:
            logger.error(
                "注册发码 SMTP 失败：email=%s error_type=%s",
                email,
                type(exc).__name__,
            )
            try:
                cancel_code_issue(issued.email, issued.request_id)
            except Exception as cancel_exc:  # noqa: BLE001
                logger.error(
                    "注册发码 SMTP 失败后回滚验证码失败：email=%s error_type=%s",
                    email,
                    type(cancel_exc).__name__,
                )
            return _fail(503, "验证码发送失败，请稍后重试")

        return _ok(
            _SEND_CODE_GENERIC_MESSAGE,
            {"expires_in": issued.expires_in},
        )

    except CooldownActiveError as exc:
        return _fail(
            429,
            "发送过于频繁，请稍后再试",
            {"retry_after": exc.retry_after},
        )
    except RedisUnavailableError:
        return _fail(503, "验证码服务暂不可用，请稍后重试")
    except EmailCodeConfigError:
        logger.error("注册发码配置错误：缺少或无效的验证码 HMAC 配置")
        return _fail(503, "验证码服务暂不可用，请稍后重试")
    except RedisError:
        logger.exception("注册发码 Redis 错误：email=%s", email)
        return _fail(503, "验证码服务暂不可用，请稍后重试")
    except Exception:
        logger.exception("注册发码未预期错误：email=%s", email)
        return _fail(500, "服务暂时不可用，请稍后重试")


# 验码成功后的邮箱/用户名冲突与 IntegrityError 共用，避免可区分枚举文案
_REGISTER_CONFLICT_MESSAGE = (
    "邮箱或用户名已被占用，请更换后重新获取验证码"
)
# 验证码非 OK 状态对外统一文案，避免通过 EXPIRED/INVALID/EXHAUSTED 推断是否有码
_REGISTER_CODE_FAIL_MESSAGE = "验证码无效或已过期，请重新获取"


@router.post("/register")
def register(data: RegisterRequest):
    """
    校验邮箱验证码后创建用户。

    成功不签发 JWT；用户使用现有 /login（username + password）。
    必须先验码再查重，避免无验证码探测邮箱/用户名是否存在。
    验证码已消费但 MySQL 创建失败时，需重新发码，不会自动重试消费。
    """

    email = str(data.email).strip().lower()
    username = data.username.strip()

    try:
        result = verify_and_consume_code(email, data.code)
    except RedisUnavailableError:
        return _fail(503, "验证码服务暂不可用，请稍后重试")
    except EmailCodeConfigError:
        logger.error("注册校验配置错误：缺少或无效的验证码 HMAC 配置")
        return _fail(503, "验证码服务暂不可用，请稍后重试")
    except RedisError:
        logger.exception("注册校验 Redis 错误：email=%s", email)
        return _fail(503, "验证码服务暂不可用，请稍后重试")

    if result.status != VerifyStatus.OK:
        logger.info(
            "注册验码未通过：email=%s status=%s",
            email,
            result.status.value,
        )
        return _fail(400, _REGISTER_CODE_FAIL_MESSAGE)

    # 验证码已消费：此后冲突/DB 失败不能用同一验证码重试
    if get_user_by_email(email) is not None:
        return _fail(409, _REGISTER_CONFLICT_MESSAGE)
    if get_user_by_username(username) is not None:
        return _fail(409, _REGISTER_CONFLICT_MESSAGE)

    try:
        password_hash = hash_password(data.password)
        user_id = create_user(
            username=username,
            password_hash=password_hash,
            email=email,
        )
    except IntegrityError:
        logger.warning(
            "注册唯一约束冲突（验证码已消费）：email=%s username=%s",
            email,
            username,
        )
        return _fail(409, _REGISTER_CONFLICT_MESSAGE)
    except Exception:
        logger.exception(
            "注册写入用户失败（验证码已消费）：email=%s username=%s",
            email,
            username,
        )
        return _fail(
            500,
            "注册失败，请重新获取验证码后再试",
        )

    return _ok(
        "注册成功，请使用用户名和密码登录",
        {
            "user_id": user_id,
            "username": username,
        },
    )
